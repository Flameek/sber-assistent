"""Retrieval metrics independent of LLM generation and refusal logic."""
import argparse
import json
import statistics
import time

from .backend import Elastic, Local
from .corpus import ROOT, chunks, seed
from .service import rank


def benchmark(method='tfidf', engine=None, k=3, split='holdout'):
    if k < 1:
        raise ValueError('k должен быть больше нуля')
    engine = engine or Local()
    search = rank
    if method == 'fasttext':
        from .embeddings import FastTextSearch
        search = FastTextSearch().rank
    cases = json.loads((ROOT/'data/retrieval-questions.json').read_text(encoding='utf-8'))
    rows = chunks(seed())
    details = []
    for case in cases:
        if case['split'] != split or not case['relevant']:
            continue
        started = time.perf_counter()
        visible = engine.candidates(rows, case['role'], case['area'])
        found = [r['ref'] for _, r in search(visible, case['question'])[:k]]
        gold = set(case['relevant'])
        hits = len(gold & set(found))
        details.append({'id': case['id'], 'precision_at_k': hits/k, 'recall_at_k': hits/len(gold),
                        'mrr': next((1/i for i, ref in enumerate(found, 1) if ref in gold), 0),
                        'ranked': found, 'ms': round((time.perf_counter()-started)*1000, 2)})
    mean = lambda field: round(statistics.mean(r[field] for r in details), 3) if details else None
    return {'method': method, 'split': split, 'k': k, 'queries': len(details),
            'precision_at_k': mean('precision_at_k'), 'recall_at_k': mean('recall_at_k'),
            'mrr_at_k': mean('mrr'), 'median_ms': statistics.median(r['ms'] for r in details) if details else None,
            'rows': details}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--method', choices=('tfidf','fasttext'), default='tfidf')
    parser.add_argument('--backend', choices=('local','elastic'), default='local')
    parser.add_argument('--split', default='holdout')
    parser.add_argument('--k', type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.method, Elastic() if args.backend=='elastic' else Local(), args.k, args.split), ensure_ascii=False, indent=2))
