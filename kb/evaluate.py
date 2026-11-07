"""Measure retrieval and expected outcomes; never label this as LLM accuracy."""
import argparse
import json
import statistics
import time

from .backend import Elastic, Local
from .corpus import ROOT, chunks, seed
from .service import Service


def evaluate(engine, split='holdout', k=3):
    if not isinstance(k, int) or k < 1:
        raise ValueError('k должен быть положительным целым')
    service = Service(chunks(seed()), engine)
    cases = [q for q in json.loads((ROOT / 'data/questions.json').read_text(encoding='utf-8')) if q['split'] == split]
    rows, precision, recall, reciprocal, times = [], [], [], [], []
    for q in cases:
        started = time.perf_counter()
        result = service.ask(q['role'], q['question'])
        times.append(1000 * (time.perf_counter() - started))
        gold = set(q['relevant'])
        found = result['ranked'][:k]
        if gold:
            hits = len(gold & set(found))
            precision.append(hits / k)
            recall.append(hits / len(gold))
            reciprocal.append(next((1 / i for i, ref in enumerate(found, 1) if ref in gold), 0))
        sources = [s['ref'] for s in result['sources']]
        source_ok = set(sources) == gold
        parts_ok = 'expected_parts' not in q or [p['kind'] for p in result['parts']] == q['expected_parts']
        ok = result['kind'] == q['expected'] and source_ok and parts_ok
        rows.append({'id': q['id'], 'expected': q['expected'], 'got': result['kind'],
                     'source': result['source'], 'sources': sources, 'ranked': found, 'ok': ok})
    mean = lambda values: round(statistics.mean(values), 3) if values else None
    return {'split': split, 'queries': len(rows), 'answerable': len(recall), 'k': k,
            'precision_at_k': mean(precision), 'recall_at_k': mean(recall), 'mrr_at_k': mean(reciprocal),
            'correct': sum(r['ok'] for r in rows), 'behavior_accuracy': mean([r['ok'] for r in rows]),
            'median_ms': round(statistics.median(times), 2) if times else None, 'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', choices=('elastic', 'local'), default='local')
    parser.add_argument('--split', choices=('dev', 'holdout', 'regression'), default='holdout')
    parser.add_argument('--k', type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(evaluate(Elastic() if args.backend == 'elastic' else Local(), args.split, args.k), indent=2, ensure_ascii=False))
