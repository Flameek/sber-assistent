"""Подбор порога смыслового поиска (KB_SEMANTIC_THRESHOLD) для модели KB_EMBED_MODEL.

Используются только НАСТРОЕЧНЫЕ вопросы: data/questions.json (dev, holdout, regression),
data/retrieval-questions.json и data/tuning-questions.json (перефразировки и ловушки для этого
подбора). Закрытый набор data/closed-questions.json здесь не участвует:
по нему только меряем итог, иначе он перестанет быть независимой проверкой.

Цена ошибок задана заранее:
  неверный ответ (ответили, хотя нельзя, или не той инструкцией) — 2: стажёр сделает не то;
  пропущенный ответ (сказали «нет ответа», хотя он есть)       — 1: стажёр спросит людей;
  прочие расхождения                                             — 1.
Из порогов с наименьшей ценой берётся середина: так выбор устойчивее к случайным колебаниям.

Запуск: python scripts/tune_semantic.py [от] [до] [шаг]      (по умолчанию 0.40 0.75 0.01)
Режим поиска без LLM: смысловой шаг работает до модели, а так перебор идёт быстро.
"""
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kb import semantic
from kb.backend import Local
from kb.corpus import ROOT
from kb.rag import Assistant
from kb.store import Store


def tuning_cases():
    cases = {}
    for name in ('data/questions.json', 'data/retrieval-questions.json', 'data/tuning-questions.json'):
        for case in json.loads((ROOT / name).read_text(encoding='utf-8')):
            if case['question'].strip():
                key = (case['role'], case.get('area', 'реестр'), case['question'])
                cases[key] = {**case, 'area': case.get('area', 'реестр')}
    return list(cases.values())


def errors(assistant, cases):
    wrong = missed = other = 0
    failures = []
    for case in cases:
        result = assistant.ask(case['role'], case['question'], case['area'])
        got = {s['ref'] for s in result['sources']}
        if result['kind'] == case['expected'] and (case['expected'] != 'answer' or got == set(case['relevant'])):
            continue
        if result['kind'] == 'answer':
            wrong += 1
        elif case['expected'] in ('answer', 'partial') and result['kind'] == 'missing':
            missed += 1
        else:
            other += 1
        failures.append(f"  {case['id']} [{case['area']}] {case['question']} -> ждали {case['expected']}, "
                        f"получили {result['kind']} {sorted(got)}")
    return wrong, missed, other, failures


def main():
    start, stop, step = (float(x) for x in (sys.argv[1:4] if len(sys.argv) >= 4 else ('0.40', '0.75', '0.01')))
    os.environ['KB_SEMANTIC'] = '1'
    cases = tuning_cases()
    print(f'Модель: {semantic.MODEL_NAME}. Настроечных вопросов: {len(cases)}')
    print('порог   неверных  пропущено  прочих  цена')
    results = []
    with tempfile.TemporaryDirectory() as directory:
        assistant = Assistant(Store(Path(directory) / 'tune.sqlite'), Local(), search_only=True)
        threshold = start
        while threshold <= stop + 1e-9:
            semantic.THRESHOLD = threshold
            wrong, missed, other, _ = errors(assistant, cases)
            cost = 2 * wrong + missed + other
            results.append((cost, round(threshold, 3)))
            print(f'{threshold:.2f}   {wrong:>5}     {missed:>5}     {other:>4}   {cost:>4}')
            threshold += step
        best_cost = min(cost for cost, _ in results)
        best = statistics.median(t for cost, t in results if cost == best_cost)
        print(f'\nНаименьшая цена {best_cost}; середина лучших порогов: {best:.2f}')
        semantic.THRESHOLD = best
        print('Ошибки при этом пороге:')
        print('\n'.join(errors(assistant, cases)[3]) or '  нет')


if __name__ == '__main__':
    main()
