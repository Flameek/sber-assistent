"""Эмбеддинги: смысловая близость вопроса и разделов инструкций.

Модель скачивается один раз в кэш Hugging Face, дальше работает без интернета.
Модель можно сменить переменной окружения KB_EMBED_MODEL.
"""
import os
from functools import lru_cache

MODEL_NAME = os.getenv("KB_EMBED_MODEL", "deepvk/USER-base")

# Пороги уверенности подобраны скриптом scripts/tune_threshold.py на dev + holdout + dev2:
# середина участка с наименьшей ценой ошибок. У каждой модели свой масштаб оценок,
# поэтому и порог у каждой свой.
THRESHOLDS = {
    "deepvk/USER-base": 0.61,
    "intfloat/multilingual-e5-base": 0.86,
}
DEFAULT_THRESHOLD = THRESHOLDS.get(MODEL_NAME, 0.5)

# Векторы уже посчитанных разделов: текст -> вектор. Инструкции меняются редко,
# поэтому каждый раздел кодируется один раз за всё время работы приложения.
_passage_cache = {}


@lru_cache(maxsize=1)
def model():
    # Импорт внутри функции: без гибридного режима PyTorch вообще не загружается.
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def passage_text(row):
    return "passage: " + row["title"] + ". " + row["text"]


def similarities(rows, question):
    """Косинусная близость вопроса к каждому разделу, в том же порядке, что rows."""
    import numpy as np

    texts = [passage_text(r) for r in rows]
    new = [t for t in dict.fromkeys(texts) if t not in _passage_cache]
    if new:
        # prompt="" отключает приставки из настроек модели — свои мы добавляем сами.
        vectors = model().encode(new, normalize_embeddings=True, prompt="")
        _passage_cache.update(zip(new, vectors))
    q = model().encode("query: " + question, normalize_embeddings=True, prompt="")
    return np.array([_passage_cache[t] for t in texts]) @ q