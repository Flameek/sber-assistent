"""Оценка ассистента на размеченных вопросах.

Наборы (split):
  dev     — вопросы, на которых настраивали поиск;
  holdout — отложенные вопросы из исходного проекта;
  stress  — сложные перефразировки, ловушки и попытки утечки (data/stress.json).
"""
import argparse
import json
import statistics
import time
from collections import defaultdict

from .backend import Elastic, Local
from .corpus import ROOT, chunks, seed
from .service import Service

QUESTION_FILES = ("data/questions.json", "data/stress.json")


def load_questions(split):
    questions = []
    for name in QUESTION_FILES:
        path = ROOT / name
        if path.exists():
            questions += json.loads(path.read_text(encoding="utf-8"))
    return [q for q in questions if q["split"] == split]


def mean(values):
    return round(statistics.mean(values), 3) if values else None


def evaluate(engine, split="holdout", k=3, ranker=None):
    all_rows = chunks(seed())
    # Кому на самом деле разрешён каждый раздел — для независимой проверки утечек.
    roles_by_ref = {row["ref"]: row["roles"] for row in all_rows}
    service = Service(all_rows, engine, ranker)

    results = []
    precision, recall, hit1, reciprocal_ranks, times = [], [], [], [], []
    by_type = defaultdict(lambda: [0, 0])  # тип -> [правильно, всего]

    for q in load_questions(split):
        start = time.perf_counter()
        answer = service.ask(q["role"], q["question"])
        times.append(1000 * (time.perf_counter() - start))

        gold = set(q["relevant"])
        ranked = answer["ranked"]

        # Метрики поиска считаем только там, где есть правильный раздел.
        if gold:
            hits = len(gold & set(ranked[:k]))
            precision.append(hits / k)
            recall.append(hits / len(gold))
            hit1.append(1.0 if ranked and ranked[0] in gold else 0.0)
            position = next((i + 1 for i, ref in enumerate(ranked) if ref in gold), None)
            reciprocal_ranks.append(1 / position if position else 0.0)

        # Утечка: в выдаче оказался раздел, который этой роли не положен.
        leaked = [ref for ref in ranked if q["role"] not in roles_by_ref.get(ref, [])]

        ok = answer["kind"] == q["expected"] and (not gold or answer["source"] in gold)
        kind = q.get("type", "base")
        by_type[kind][0] += ok
        by_type[kind][1] += 1

        results.append({
            "id": q["id"], "type": kind, "question": q["question"],
            "expected": q["expected"], "got": answer["kind"],
            "source": answer["source"], "ranked": ranked[:k],
            "leaked": leaked, "ok": ok,
        })

    return {
        "split": split,
        "ranker": service.ranker,
        "queries": len(results),
        "answerable": len(recall),
        "k": k,
        "correct": sum(r["ok"] for r in results),
        "hit_at_1": mean(hit1),
        "mrr": mean(reciprocal_ranks),
        "precision_at_k": mean(precision),
        "recall_at_k": mean(recall),
        "leaks": sum(bool(r["leaked"]) for r in results),
        "by_type": {t: f"{ok}/{total}" for t, (ok, total) in sorted(by_type.items())},
        "median_ms": round(statistics.median(times), 2) if times else None,
        "rows": results,
    }


def print_summary(report):
    print(f"Набор: {report['split']} ({report['ranker']})  |  верно {report['correct']}/{report['queries']}"
          f"  |  hit@1 {report['hit_at_1']}  |  MRR {report['mrr']}"
          f"  |  recall@{report['k']} {report['recall_at_k']}  |  утечек {report['leaks']}")
    print("По типам:", ", ".join(f"{t} {v}" for t, v in report["by_type"].items()))
    print("Ошибки:")
    for r in report["rows"]:
        if not r["ok"]:
            print(f"  {r['id']} [{r['type']}] {r['question']}  ->  ждали {r['expected']},"
                  f" получили {r['got']} ({r['source']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("elastic", "local"), default="local")
    parser.add_argument("--split", choices=("dev", "holdout", "stress"), default="holdout")
    parser.add_argument("--ranker", choices=("tfidf", "hybrid"), default=None,
                        help="метод поиска; по умолчанию из KB_RANKER или tfidf")
    parser.add_argument("--summary", action="store_true", help="коротко, вместо полного JSON")
    args = parser.parse_args()
    engine = Elastic() if args.backend == "elastic" else Local()
    report = evaluate(engine, args.split, ranker=args.ranker)
    if args.summary:
        print_summary(report)
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))