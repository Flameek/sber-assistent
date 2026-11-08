"""Durable documents and review decisions. Profiles are demo actors, not authentication."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3

from .corpus import ROLES, chunks, seed
from .topics import TOPICS


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def validate(doc):
    if not isinstance(doc, dict):
        raise ValueError('Ожидается один JSON-объект')

    def word(value):
        return isinstance(value, str) and re.fullmatch(r'[a-z0-9_-]{1,48}', value)

    if not word(doc.get('id')) or not word(doc.get('rule')):
        raise ValueError('Некорректные id или rule')
    if type(doc.get('version')) is not int or not 1 <= doc['version'] <= 100000:
        raise ValueError('Неверная версия')
    if type(doc.get('priority')) is not int or not 1 <= doc['priority'] <= 100:
        raise ValueError('Приоритет должен быть от 1 до 100')
    roles = doc.get('roles')
    if not isinstance(roles, list) or not roles or any(not isinstance(r, str) or r not in ROLES for r in roles):
        raise ValueError('Неизвестная роль')
    for field in ('title', 'contact'):
        if not isinstance(doc.get(field), str) or not 1 <= len(doc[field].strip()) <= 180:
            raise ValueError('Проверьте поле ' + field)
    if not isinstance(doc.get('area'), str) or not re.fullmatch(r'[a-zа-яё0-9_-]{1,64}', doc['area']):
        raise ValueError('Область: до 64 строчных букв, цифр, дефисов или подчёркиваний')
    sections = doc.get('sections')
    if not isinstance(sections, list) or not 1 <= len(sections) <= 30:
        raise ValueError('Нужно от 1 до 30 разделов')
    cleaned = []
    seen = set()
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError('Раздел должен быть объектом')
        if set(section) - {'key', 'text', 'topic', 'facts'}:
            raise ValueError('Раздел может содержать только key, text, topic, facts; права задаются на уровне документа')
        if not word(section.get('key')) or section['key'] in seen:
            raise ValueError('Проверьте ключ раздела')
        if not isinstance(section.get('text'), str) or not 1 <= len(section['text'].strip()) <= 5000:
            raise ValueError('Проверьте текст раздела')
        seen.add(section['key'])
        item = {'key': section['key'], 'text': section['text']}
        if 'topic' in section:
            if not word(section['topic']):
                raise ValueError('Некорректный идентификатор темы раздела')
            item['topic'] = section['topic']
        if 'facts' in section:
            facts = section['facts']
            if not isinstance(facts, dict) or len(facts) > 20 or any(
                not word(k) or not isinstance(v, str) or not 1 <= len(v.strip()) <= 180
                for k, v in facts.items()
            ):
                raise ValueError('facts: до 20 коротких пар ключ — строковое значение')
            item['facts'] = facts
        cleaned.append(item)
    result = {k: doc[k] for k in ('id', 'rule', 'version', 'priority', 'title', 'contact', 'roles', 'area')}
    result['sections'] = cleaned
    return result


class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('KB_DB', '.local/handbook.sqlite'))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS docs (id TEXT, v INTEGER, body TEXT NOT NULL, PRIMARY KEY(id,v))')
            db.execute('CREATE TABLE IF NOT EXISTS proposals (n INTEGER PRIMARY KEY, body TEXT NOT NULL, state TEXT NOT NULL)')
            # Additive migration preserves existing documents, proposals and decisions.
            columns = {r[1] for r in db.execute('PRAGMA table_info(proposals)')}
            for column in ('author', 'reviewer', 'comment', 'created_at', 'resolved_at'):
                if column not in columns:
                    db.execute(f"ALTER TABLE proposals ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
            if not db.execute('SELECT 1 FROM docs LIMIT 1').fetchone():
                for raw in seed():
                    doc = validate(raw)
                    db.execute('INSERT OR IGNORE INTO docs VALUES (?,?,?)',
                               (doc['id'], doc['version'], json.dumps(doc, ensure_ascii=False)))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def published(self):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT body FROM docs ORDER BY id,v')]

    def propose(self, doc, actor, author=None):
        if actor not in (*ROLES, 'lead'):
            raise PermissionError('Неизвестный профиль')
        doc = validate(doc)
        with self.db() as db:
            return db.execute("INSERT INTO proposals(body,state,author,created_at) VALUES (?,'pending',?,?)",
                              (json.dumps(doc, ensure_ascii=False), author or actor, now())).lastrowid

    def pending(self, actor):
        return [(r['n'], r['document']) for r in self.reviews(actor) if r['state'] == 'pending']

    def reviews(self, actor):
        if actor != 'lead':
            raise PermissionError('Только тимлид')
        with self.db() as db:
            db.row_factory = sqlite3.Row
            records = [dict(r) for r in db.execute('SELECT * FROM proposals ORDER BY n DESC')]
        for record in records:
            record['document'] = json.loads(record.pop('body'))
        return records

    def approve(self, n, actor, reviewer=None):
        if actor != 'lead':
            raise PermissionError('Только тимлид')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT body FROM proposals WHERE n=? AND state='pending'", (n,)).fetchone()
            if not row:
                raise ValueError('Предложение уже обработано или отсутствует')
            doc = validate(json.loads(row[0]))
            old = db.execute('SELECT MAX(v) FROM docs WHERE id=?', (doc['id'],)).fetchone()[0]
            if old is not None and doc['version'] <= old:
                raise ValueError('Версия должна быть новее опубликованной')
            current = [json.loads(r[0]) for r in db.execute('SELECT body FROM docs')]
            if len(chunks([*current, doc])) > 1000:
                raise ValueError('Лимит учебной базы — 1000 действующих разделов. Документ не опубликован.')
            db.execute('INSERT INTO docs VALUES (?,?,?)', (doc['id'], doc['version'], json.dumps(doc, ensure_ascii=False)))
            db.execute("UPDATE proposals SET state='approved',reviewer=?,resolved_at=? WHERE n=?",
                       (reviewer or actor, now(), n))

    def reject(self, n, actor, comment, reviewer=None):
        if actor != 'lead':
            raise PermissionError('Только тимлид')
        if not isinstance(comment, str) or not 1 <= len(comment.strip()) <= 1000:
            raise ValueError('Укажите причину отклонения, до 1000 символов')
        with self.db() as db:
            cursor = db.execute("UPDATE proposals SET state='rejected',reviewer=?,comment=?,resolved_at=? WHERE n=? AND state='pending'",
                                (reviewer or actor, comment.strip(), now(), n))
            if cursor.rowcount != 1:
                raise ValueError('Предложение уже обработано или отсутствует')
