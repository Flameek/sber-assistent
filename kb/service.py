"""Offline retrieval with explicit operation scopes and cited, extractive answers."""
from collections import Counter
from functools import lru_cache
import math
import re
import pymorphy3

from .topics import TOPICS, normalize, query_topics, row_topic

STOP = set('как где куда какой какая какие какому по за на и или у я кто мне для мои моя мою надо нужно нужен бы уже реестр инцидент стажер учебный учебного пожалуйста что это затем'.split())
FORMS = [
    (r"инцидент.*|реестр.*|учебн.*|стаж[её]р.*", None),
    (r"статус.*|состоян.*|этап.*", "статус"),
    (r"регистрир.*|зарегистр.*|созда.*|регистрац.*|завест.*", "регистрация"),
    (r"прав[аоыу]?|доступ.*", "доступ"),
    (r"эскалац.*|эскалир.*", "эскалация"),
    (r"классифи.*|категор.*", "категория"),
    (r"заявк.*|заявок", "заявка"), (r"карточк.*", "карточка"),
    (r"влиян.*", "влияние"), (r"критическ.*", "критический"),
    (r"чтени.*", "чтение"),
    (r"провер.*|посмотр.*|узна.*|отслед.*", "проверить"),
    (r"получ.*|запрос.*|оформ.*", "запросить"),
    (r"войти|вход.*|входи.*", "вход"),
    (r"экспорт.*|выгруз.*", "экспорт"),
    (r"разобра.*|разбор.*|анализ.*", "разбор"),
    (r"подключ.*|соедин.*", "подключение"),
]


@lru_cache(maxsize=1)
def morph():
    return pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=32000)
def lemma(token):
    return morph().parse(token)[0].normal_form if re.fullmatch(r'[а-я]+', token) else token


def terms(text):
    out = []
    for term in re.findall(r"[a-zа-я0-9-]+", normalize(text)):
        if term in STOP or len(term) < 3:
            continue
        for pattern, value in FORMS:
            if re.fullmatch(pattern, term):
                term = value
                break
        if term:
            out.append(lemma(term))
    return out


def magnitude(vector):
    return math.sqrt(sum(x * x for x in vector.values())) or 1


@lru_cache(maxsize=64)
def document_vectors(documents):
    """Cache by visible text snapshot, not by a mutable user/profile object."""
    counters = [Counter(terms(title + ' ' + title + ' ' + body)) for title, body in documents]
    df = Counter(term for doc in counters for term in doc)
    weights = {t: 1 + math.log((1 + len(documents)) / (1 + count)) for t, count in df.items()}
    vectors = [{t: (1 + math.log(n)) * weights[t] for t, n in d.items()} for d in counters]
    return weights, vectors, [magnitude(v) for v in vectors]


def rank(rows, question):
    if not rows:
        return []
    weights, vectors, norms = document_vectors(tuple((r['title'], r['text']) for r in rows))
    q = Counter(terms(question))
    vq = {t: (1 + math.log(n)) * weights.get(t, 1 + math.log(1 + len(rows))) for t, n in q.items()}
    qnorm = magnitude(vq)
    ranked = []
    for row, vector, norm in zip(rows, vectors, norms):
        score = sum(vq[t] * vector[t] for t in vq.keys() & vector.keys()) / (qnorm * norm)
        if score > 0:
            ranked.append((score, row))
    return sorted(ranked, key=lambda pair: (-pair[0], pair[1]['ref']))


def requests(question):
    """Split action clauses, while keeping 'категория и влияние' together."""
    action = r"как\b|где\b|сколько\b|почему\b|что\b|получ|запрос|отозв|провер|узна|зарегистр|созда|удал|оформ|классифиц|эскалир"
    clauses = re.split(r"[?;]+|\s+(?:и\s+затем|а\s+затем|затем|потом|а\s+также|и)\s+(?=" + action + r")", normalize(question))
    output = []
    for clause in clauses:
        clause = clause.strip(' ,.!')
        if not clause:
            continue
        probe = clause
        # The noun can be shared: 'получить и отозвать доступ'.
        if re.search(r"доступ|права", normalize(question)) and re.fullmatch(r"(?:как\s+)?(?:получить|запросить|отозвать)", clause):
            probe += ' доступ'
        topics = query_topics(probe)
        output.extend((probe, topic) for topic in topics)
        if not topics:
            output.append((clause, None))
    return list(dict.fromkeys(output))


class Service:
    def __init__(self, rows, engine):
        self.rows = rows
        self.engine = engine

    def visible(self, role):
        return self.engine.candidates(self.rows, role, 'реестр')

    def source(self, role, ref):
        return next((r for r in self.visible(role) if r['ref'] == ref), None)

    @staticmethod
    def missing(question, topic=None):
        return {'kind': 'missing', 'question': question, 'topic': topic,
                'text': 'В доступных инструкциях нет подтверждённого ответа. Обратитесь в службу сопровождения учебного реестра.',
                'sources': [], 'ranked': [], 'explanation': 'Похожее название операции не подтверждает порядок её выполнения.'}

    def answer_topic(self, rows, question, topic):
        missing = self.missing(question, topic)
        scoped = [r for r in rows if row_topic(r) == topic] if topic else []
        if not scoped:
            return missing
        ranked = rank(scoped, question)
        if not ranked or ranked[0][0] < 0.10:
            return missing
        refs = [r['ref'] for _, r in ranked]
        highest = max(r['priority'] for r in scoped)
        winners = [r for r in scoped if r['priority'] == highest]
        # Compare the same operation (topic), even across different legacy rules.
        # Facts are explicitly authored assertions, not an automatic semantic check.
        assertions = {}
        for row in winners:
            for key, value in row.get('facts', {}).items():
                assertions.setdefault(key, set()).add(normalize(value))
        contradicted = sorted(key for key, values in assertions.items() if len(values) > 1)
        by_document = {}
        for item in winners:
            by_document.setdefault(item['id'], []).append(item)
        distinct = {tuple(normalize(r['text']) for r in sorted(items, key=lambda r: r['key']))
                    for items in by_document.values()}
        if contradicted or len(distinct) > 1:
            contact = 'Тимлид ИБ'
            explicit = bool(contradicted)
            text = ('Доступные инструкции одинакового приоритета расходятся. Передайте вопрос тимлиду ИБ.' if explicit else
                    'Есть разные формулировки в инструкциях одинакового приоритета. Их совместимость не подтверждена. Передайте вопрос тимлиду ИБ.')
            return {'kind': 'conflict' if explicit else 'clarify', 'question': question, 'topic': topic,
                    'text': text, 'sources': [], 'ranked': refs,
                    'explanation': 'Источники: ' + ', '.join(r['ref'] for r in winners) +
                    ('. Различаются факты: ' + ', '.join(contradicted) if explicit else '. Нужна проверка редактора.'),
                    'contact': contact}
        ordered = rank(winners, question)
        if not ordered:
            return missing
        row = ordered[0][1]
        selected = sorted(by_document[row['id']], key=lambda r: r['key'])
        contact = row['contact']
        lower = [r['ref'] for r in scoped if r['priority'] < highest]
        explanation = f"Выбран {row['ref']}: актуальная версия документа, приоритет {highest}."
        if len(selected) > 1:
            explanation += ' Разделы одной операции из выбранного документа приведены вместе.'
        if lower:
            explanation += ' Источники меньшего приоритета не использованы: ' + ', '.join(lower) + '.'
        # Final source leads the evaluated ranking, after priority resolution.
        refs = list(dict.fromkeys([r['ref'] for r in selected] + refs))
        return {'kind': 'answer', 'question': question, 'topic': topic, 'text': '\n\n'.join(r['text'] for r in selected),
                'sources': [{'ref': r['ref'], 'title': r['title'], 'version': r['version'],
                             'section': r['key'], 'priority': highest} for r in selected],
                'ranked': refs, 'explanation': explanation, 'contact': contact}

    def ask(self, role, question):
        if not isinstance(question, str) or len(question) > 2000:
            raise ValueError('Вопрос должен быть строкой не длиннее 2000 символов')
        rows = self.visible(role)
        if not question.strip():
            available = list(dict.fromkeys(row_topic(r) for r in rows if row_topic(r)))
            parts = [{'kind': 'clarify', 'question': question, 'topic': None,
                      'text': 'Уточните вопрос: какую операцию нужно выполнить?', 'sources': [], 'ranked': [],
                      'explanation': 'Доступные темы: ' + ', '.join(TOPICS[t] for t in available)}]
        else:
            parts = [self.answer_topic(rows, clause, topic) for clause, topic in requests(question)]
            if not parts:
                parts = [self.missing(question)]
        sources = list({s['ref']: s for p in parts for s in p['sources']}.values())
        kinds = {p['kind'] for p in parts}
        kind = parts[0]['kind'] if len(kinds) == 1 else 'partial'
        if len(parts) == 1:
            text = parts[0]['text']
        else:
            text = '\n\n'.join(f"{i}. {TOPICS.get(p['topic'], p['question'])}\n{p['text']}" for i, p in enumerate(parts, 1))
        return {'kind': kind, 'text': text, 'source': sources[0]['ref'] if len(sources) == 1 else None,
                'sources': sources, 'parts': parts,
                'ranked': list(dict.fromkeys(ref for p in parts for ref in p['ranked'])),
                'explanation': '\n\n'.join(p['explanation'] for p in parts)}
