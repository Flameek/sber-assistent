"""Reproducible FastText baseline, trained locally on the synthetic corpus."""
import argparse
import json
from pathlib import Path

from .corpus import chunks, digest, seed, token_hash
from .service import terms


def train(path, dimensions=64, epochs=40):
    from gensim.models import FastText
    rows = chunks(seed())
    sentences = [terms(r['title'] + ' ' + r['text']) for r in rows]
    model = FastText(vector_size=dimensions, window=4, min_count=1, workers=1,
                     seed=42, hashfxn=token_hash, bucket=10000, min_n=3, max_n=5, sg=1)
    model.build_vocab(corpus_iterable=sentences)
    model.train(corpus_iterable=sentences, total_examples=len(sentences), epochs=epochs)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(path))
    path.with_suffix('.json').write_text(json.dumps({'corpus': digest(rows), 'dimensions': dimensions,
        'epochs': epochs, 'seed': 42, 'workers': 1, 'training_chunks': len(rows)}, indent=2))


class FastTextSearch:
    def __init__(self, path='.local/fasttext.model'):
        from gensim.models import FastText
        self.model = FastText.load(str(path))

    def rank(self, rows, question):
        import numpy as np
        def vector(text):
            tokens = terms(text)
            return np.mean([self.model.wv[token] for token in tokens], axis=0) if tokens else np.zeros(self.model.vector_size)
        q = vector(question)
        qnorm = np.linalg.norm(q)
        if not qnorm:
            return []
        result = []
        for row in rows:
            d = vector(row['title'] + ' ' + row['text'])
            score = float(np.dot(q, d) / (qnorm * (np.linalg.norm(d) or 1)))
            result.append((score, row))
        return sorted(result, key=lambda pair: (-pair[0], pair[1]['ref']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='.local/fasttext.model')
    args = parser.parse_args()
    train(args.output)
    print('FastText trained:', args.output)
