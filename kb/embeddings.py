"""Эмбеддинги: смысловая близость вопроса и разделов инструкций.

Два вида моделей:
  * navec — классические векторы слов (как Word2Vec/GloVe): вектор текста = среднее векторов его слов.
    Лёгкая (~50 МБ), без PyTorch. Файл модели кладётся в models/ (см. README).
  * трансформерные модели (deepvk/USER-base, intfloat/multilingual-e5-base) — кодируют предложение
    целиком, с учётом порядка и контекста слов. Нужен пакет из requirements-ml.txt.

Модель выбирается переменной окружения KB_EMBED_MODEL. Всё работает без интернета,
трансформерная модель скачивается один раз в кэш Hugging Face.
"""
import os
from functools import lru_cache
from pathlib import Path

MODEL_NAME = os.getenv("KB_EMBED_MODEL", "deepvk/USER-base")
NAVEC_PATH = os.getenv(
    "KB_NAVEC_PATH",
    str(Path(__file__).resolve().parents[1] / "models" / "navec_hudlit_v1_12B_500K_300d_100q.tar"),
)

# Пороги уверенности подобраны скриптом scripts/tune_threshold.py на dev + holdout + dev2:
# середина участка с наименьшей ценой ошибок. У каждой модели свой масштаб оценок,
# поэтому и порог у каждой свой.
THRESHOLDS = {
    "navec": 0.75,
    "deepvk/USER-base": 0.61,
    "intfloat/multilingual-e5-base": 0.86,
}
DEFAULT_THRESHOLD = THRESHOLDS.get(MODEL_NAME, 0.5)

# Векторы уже посчитанных разделов: текст -> вектор. Инструкции меняются редко,
# поэтому каждый раздел кодируется один раз за всё время работы приложения.
_passage_cache = {}


@lru_cache(maxsize=1)
def transformer():
    # Импорт внутри функции: без гибридного режима PyTorch вообще не загружается.
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


@lru_cache(maxsize=1)
def navec():
    from navec import Navec
    return Navec.load(NAVEC_PATH)


def navec_vector(text):
    """Средний вектор слов текста, нормированный до длины 1.

    Слова берём после той же обработки, что и в TF-IDF (начальная форма, без служебных слов),
    чтобы оба метода видели одинаковые слова.
    """
    import numpy as np
    from .service import terms

    model = navec()
    words = [w for w in terms(text) if w in model]
    if not words:
        return np.zeros(300, dtype=np.float32)
    vector = np.mean([model[w] for w in words], axis=0)
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector


def encode_passages(texts):
    if MODEL_NAME == "navec":
        return [navec_vector(t) for t in texts]
    # prompt="" отключает приставки из настроек модели — свои мы добавляем сами.
    return transformer().encode(["passage: " + t for t in texts], normalize_embeddings=True, prompt="")


def encode_query(question):
    if MODEL_NAME == "navec":
        return navec_vector(question)
    return transformer().encode("query: " + question, normalize_embeddings=True, prompt="")


def similarities(rows, question):
    """Косинусная близость вопроса к каждому разделу, в том же порядке, что rows."""
    import numpy as np

    texts = [row["title"] + ". " + row["text"] for row in rows]
    new = [t for t in dict.fromkeys(texts) if t not in _passage_cache]
    if new:
        _passage_cache.update(zip(new, encode_passages(new)))
    return np.array([_passage_cache[t] for t in texts]) @ encode_query(question)