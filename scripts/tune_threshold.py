"""Подбор порога уверенности эмбеддингов для гибридного поиска.

Порог подбирается на вопросах для настройки: dev, holdout и dev2.
stress не используется — по нему меряем итог один раз, уже с выбранным порогом.

Цена ошибок задана заранее, до подбора:
  неверный ответ (ответили, хотя нельзя, или не тем разделом) — 2 балла: стажёр сделает не то;
  пропущенный ответ (сказали «нет ответа», хотя он есть)       — 1 балл: стажёр просто спросит людей;
  прочие расхождения (например, не распознан конфликт)          — 1 балл.

Запуск: python -m scripts.tune_threshold <от> <до> <шаг>
Модель берётся из KB_EMBED_MODEL, как в приложении.
"""
import sys

import kb.service as service
from kb.backend import Local
from kb.embeddings import MODEL_NAME
from kb.evaluate import evaluate

SPLITS = ("dev", "holdout", "dev2")


def errors(rows):
    wrong = missed = other = 0
    for r in rows:
        if r["ok"]:
            continue
        if r["got"] == "answer":
            wrong += 1
        elif r["expected"] == "answer" and r["got"] == "missing":
            missed += 1
        else:
            other += 1
    return wrong, missed, other


def main():
    start, stop, step = (float(x) for x in sys.argv[1:4])
    engine = Local()
    print(f"Модель: {MODEL_NAME}")
    print("порог   верно   неверных  пропущено  прочих  цена")
    results = []
    threshold = start
    while threshold <= stop + 1e-9:
        service.SEM_THRESHOLD = threshold
        rows = []
        for split in SPLITS:
            rows += evaluate(engine, split, ranker="hybrid")["rows"]
        wrong, missed, other = errors(rows)
        cost = 2 * wrong + missed + other
        correct = sum(r["ok"] for r in rows)
        results.append((cost, -threshold, threshold))
        print(f"{threshold:.3f}   {correct:>2}/{len(rows)}   {wrong:>5}     {missed:>5}     {other:>4}   {cost:>4}")
        threshold += step
    best = min(results)[2]  # наименьшая цена; при равенстве — более строгий (высокий) порог
    print(f"\nЛучший порог: {best:.3f}")
    wrong_rows = []
    service.SEM_THRESHOLD = best
    for split in SPLITS:
        wrong_rows += [r for r in evaluate(engine, split, ranker="hybrid")["rows"] if not r["ok"]]
    for r in wrong_rows:
        print(f"  {r['id']} [{r['type']}] {r['question']}  ->  ждали {r['expected']}, получили {r['got']} ({r['source']})")


if __name__ == "__main__":
    main()