"""Закрытый набор вопросов (data/closed-questions.json): независимая проверка ассистента.

Набор составлен отдельно от разработки и не используется для настройки поиска или промпта.
Проверяется не только тип ответа и источники, но и содержание:
  must_contain     — что обязано быть в ответе (условия, запреты, ключевой шаг);
  must_not_contain — чего быть не должно (закрытые сведения, устаревший порядок, служебный текст).
Сравнение без учёта регистра. Полноту пересказа это не доказывает — нужен просмотр человеком.

Запуск:
  python scripts/evaluate_closed.py --mode search     поиск по инструкциям (без LLM)
  python scripts/evaluate_closed.py --mode ai         ИИ-ответ (нужна запущенная Ollama)
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from kb.backend import Local
from kb.corpus import ROOT, chunks, seed
from kb.llm import ModelError
from kb.rag import Assistant
from kb.store import Store

load_dotenv(ROOT / '.env', override=False)


def check(case, result, allowed):
    """Список найденных проблем; пустой список — вопрос пройден."""
    problems = []
    if result['kind'] != case['expected']:
        problems.append(f"тип ответа {result['kind']}, ожидался {case['expected']}")
    got = {s['ref'] for s in result['sources']}
    if case['expected'] == 'answer' and got != set(case['relevant']):
        problems.append(f"источники {sorted(got)}, ожидались {case['relevant']}")
    leaked = sorted(got - allowed)
    if leaked:
        problems.append(f"УТЕЧКА: источники вне прав роли {leaked}")
    text = result['text'].casefold()
    for phrase in case['must_contain']:
        if phrase.casefold() not in text:
            problems.append(f"нет «{phrase}»")
    for phrase in case['must_not_contain']:
        if phrase.casefold() in text:
            problems.append(f"лишнее «{phrase}»")
    return problems, bool(leaked)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('search', 'ai'), default='search')
    parser.add_argument('--output', default=None, help='куда сохранить подробный JSON (по умолчанию docs/evaluation-closed-<режим>.json)')
    args = parser.parse_args()
    cases = json.loads((ROOT / 'data/closed-questions.json').read_text(encoding='utf-8'))
    rows = chunks(seed())

    records, by_type, leaks, generated_ms = [], defaultdict(lambda: [0, 0]), 0, []
    with tempfile.TemporaryDirectory() as directory:
        assistant = Assistant(Store(Path(directory) / 'closed.sqlite'), Local(), search_only=args.mode == 'search')
        for case in cases:
            # Что роли действительно разрешено в этой системе — независимо от логики ассистента.
            allowed = {r['ref'] for r in rows if case['role'] in r['roles'] and r['area'] == case['area']}
            try:
                result = assistant.ask(case['role'], case['question'], case['area'])
                problems, leaked = check(case, result, allowed)
            except ModelError as error:
                result, problems, leaked = None, [f'ошибка модели: {error}'], False
            leaks += leaked
            by_type[case['type']][0] += not problems
            by_type[case['type']][1] += 1
            if result and result.get('generated'):
                generated_ms.append(result['elapsed_ms'])
            records.append({'id': case['id'], 'type': case['type'], 'question': case['question'],
                            'expected': case['expected'], 'ok': not problems, 'problems': problems,
                            'kind': result['kind'] if result else None,
                            'sources': [s['ref'] for s in result['sources']] if result else [],
                            'text': result['text'] if result else None, 'human_review': 'not_done'})

    passed = sum(r['ok'] for r in records)
    print(f"Режим: {args.mode}  |  пройдено {passed}/{len(records)}  |  утечек: {leaks}"
          + (f"  |  генерация, медиана: {statistics.median(generated_ms) / 1000:.1f} с" if generated_ms else ''))
    print('По типам:', ', '.join(f'{t} {ok}/{total}' for t, (ok, total) in sorted(by_type.items())))
    for r in records:
        if not r['ok']:
            print(f"  {r['id']} [{r['type']}] {r['question']}\n      -> {'; '.join(r['problems'])}")

    destination = Path(args.output or f'docs/evaluation-closed-{args.mode}.json')
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = {'mode': args.mode, 'questions': len(records), 'passed': passed, 'leaks': leaks,
              'by_type': {t: f'{ok}/{total}' for t, (ok, total) in sorted(by_type.items())},
              'note': 'Автоматическая проверка типа, источников и обязательных фраз. Нужен просмотр человеком.',
              'rows': records}
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Подробно: {destination}')


if __name__ == '__main__':
    main()
