"""Сравнение моделей эмбеддингов на dev + holdout.

stress здесь намеренно не используется: это тестовый набор, по нему мы только меряем итог.
Запуск: python -m scripts.compare_embeddings <модель> [<модель> ...]
"""
import sys

from sentence_transformers import SentenceTransformer

from kb.backend import Local
from kb.corpus import chunks, seed
from kb.evaluate import load_questions

rows = chunks(seed())
rule_of = {r["ref"]: r["rule"] for r in rows}
questions = load_questions("dev") + load_questions("holdout")
engine = Local()

for name in sys.argv[1:]:
    model = SentenceTransformer(name)
    hits, on_topic, off_topic = [], [], []

    for q in questions:
        # Ищем только среди разделов, разрешённых роли, — как в настоящем поиске.
        visible = engine.candidates(rows, q["role"], "реестр")
        P = model.encode(["passage: " + r["title"] + ". " + r["text"] for r in visible],
                         normalize_embeddings=True, prompt="")
        v = model.encode("query: " + q["question"], normalize_embeddings=True, prompt="")
        scores = P @ v
        best = int(scores.argmax())

        if q["relevant"]:
            # Попадание = лучший раздел относится к тому же правилу, что и эталон.
            # Между инструкциями одного правила дальше выбирает логика приоритетов.
            gold_rules = {rule_of[ref] for ref in q["relevant"]}
            hits.append(visible[best]["rule"] in gold_rules)
            on_topic.append(float(scores[best]))
        elif q["expected"] == "missing":
            off_topic.append(float(scores[best]))

    gap = min(on_topic) - max(off_topic)
    print(name)
    print(f"  hit@1 (по правилу): {sum(hits)}/{len(hits)}")
    print(f"  лучшая оценка: по теме от {min(on_topic):.3f}, мимо до {max(off_topic):.3f}, разрыв {gap:+.3f}")