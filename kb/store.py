"""SQLite is the durable source of approved data; publication changes the ES snapshot hash."""
import sqlite3, json, re, os
from contextlib import contextmanager
from pathlib import Path
from .corpus import seed, ROLES

def validate(doc):
    if not isinstance(doc,dict):raise ValueError("Ожидается один JSON-объект")
    def word(v):return isinstance(v,str) and re.fullmatch(r"[a-z0-9_-]{1,48}",v)
    if not word(doc.get("id")) or not word(doc.get("rule")):raise ValueError("Некорректные id или rule")
    if type(doc.get("version")) is not int or not 1<=doc["version"]<=100000:raise ValueError("Неверная версия")
    if type(doc.get("priority")) is not int or not 1<=doc["priority"]<=100:raise ValueError("Приоритет должен быть от 1 до 100")
    roles=doc.get("roles")
    if not isinstance(roles,list) or not roles or any(not isinstance(k,str) or k not in ROLES for k in roles):raise ValueError("Неизвестная роль")
    for f in ("title","contact"):
        if not isinstance(doc.get(f),str) or not 1<=len(doc[f].strip())<=180:raise ValueError("Проверьте поле "+f)
    if doc.get("area")!="реестр":raise ValueError("Неизвестная предметная область")
    ss=doc.get("sections")
    if not isinstance(ss,list) or not 1<=len(ss)<=30:raise ValueError("Нужно от 1 до 30 разделов")
    seen=set()
    for s in ss:
        if not isinstance(s,dict) or not word(s.get("key")) or s["key"] in seen or not isinstance(s.get("text"),str) or not 1<=len(s["text"].strip())<=5000:raise ValueError("Проверьте ключ и текст раздела")
        seen.add(s["key"])
    return {k:doc[k] for k in ("id","rule","version","priority","title","contact","roles","area","sections")}

class Store:
    def __init__(self,path=None):
        self.path=Path(path or os.getenv("KB_DB",".local/handbook.sqlite"))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS docs (id TEXT, v INTEGER, body TEXT NOT NULL, PRIMARY KEY(id,v))")
            db.execute("CREATE TABLE IF NOT EXISTS proposals (n INTEGER PRIMARY KEY, body TEXT NOT NULL, state TEXT NOT NULL)")
            if not db.execute("SELECT 1 FROM docs LIMIT 1").fetchone():
                for d in seed():
                    validate(d);db.execute("INSERT OR IGNORE INTO docs VALUES (?,?,?)",(d["id"],d["version"],json.dumps(d,ensure_ascii=False)))
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db:yield db
        finally:db.close()
    def published(self):
        with self.db() as db:return [json.loads(x[0]) for x in db.execute("SELECT body FROM docs ORDER BY id,v")]
    def propose(self,doc,actor):
        if actor not in (*ROLES,"lead"):raise PermissionError("Неизвестный профиль")
        d=validate(doc)
        with self.db() as db:return db.execute("INSERT INTO proposals(body,state) VALUES (?,'pending')",(json.dumps(d,ensure_ascii=False),)).lastrowid
    def pending(self,actor):
        if actor!="lead":raise PermissionError("Только тимлид")
        with self.db() as db:return [(n,json.loads(b)) for n,b in db.execute("SELECT n,body FROM proposals WHERE state='pending' ORDER BY n")]
    def approve(self,n,actor):
        if actor!="lead":raise PermissionError("Только тимлид")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT body FROM proposals WHERE n=? AND state='pending'",(n,)).fetchone()
            if not row:raise ValueError("Предложение уже обработано или отсутствует")
            d=json.loads(row[0]); old=db.execute("SELECT MAX(v) FROM docs WHERE id=?",(d["id"],)).fetchone()[0]
            if old is not None and d["version"]<=old:raise ValueError("Версия должна быть новее опубликованной")
            db.execute("INSERT INTO docs VALUES (?,?,?)",(d["id"],d["version"],row[0]))
            db.execute("UPDATE proposals SET state='approved' WHERE n=?",(n,))
