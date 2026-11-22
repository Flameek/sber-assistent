"""Смысловой поиск (эмбеддинги) — запасной шаг, когда словарь операций и TF-IDF не узнали вопрос.

Пример: «Что нужно, чтобы меня пустили в реестр?» — ни одно слово не совпадает с инструкцией
«Доступ к реестру», но по смыслу это она. Эмбеддинги находят самый близкий раздел; если сходство
выше порога, берётся его операция, и дальше работают обычные проверки: права, приоритеты, конфликты.

Включается переменной KB_SEMANTIC=1 (по умолчанию выключено). Нужен пакет из requirements-ml.txt.
Модель скачивается один раз в кэш Hugging Face, дальше всё работает без интернета.
"""
from functools import lru_cache
import os

MODEL_NAME = os.getenv('KB_EMBED_MODEL', 'deepvk/USER-base')
# Подобран scripts/tune_semantic.py на настроечных вопросах (не на закрытом наборе):
# середина участка 0.51–0.53 с наименьшей ценой ошибок для deepvk/USER-base.
THRESHOLD = float(os.getenv('KB_SEMANTIC_THRESHOLD', '0.52'))

_passages = {}  # текст раздела -> вектор; разделы меняются редко, кодируем каждый один раз


def enabled():
    return os.getenv('KB_SEMANTIC', '0') == '1'


@lru_cache(maxsize=1)
def model():
    # Импорт внутри функции: без включённого режима PyTorch вообще не загружается.
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


@lru_cache(maxsize=4096)
def encode_query(question):
    # prompt="" отключает приставку из настроек модели — свои приставки мы добавляем сами.
    return model().encode('query: ' + question, normalize_embeddings=True, prompt='')


def similarities(rows, question):
    """Косинусная близость вопроса к каждому разделу, в том же порядке, что rows."""
    import numpy as np

    texts = [r['title'] + '. ' + r['text'] for r in rows]
    new = [t for t in dict.fromkeys(texts) if t not in _passages]
    if new:
        vectors = model().encode(['passage: ' + t for t in new], normalize_embeddings=True, prompt='')
        _passages.update(zip(new, vectors))
    return np.array([_passages[t] for t in texts]) @ encode_query(question)


def best_match(rows, question):
    """Самый близкий по смыслу раздел среди разрешённых rows: (раздел, сходство)."""
    if not rows:
        return None, 0.0
    scores = similarities(rows, question)
    best = max(range(len(rows)), key=lambda i: scores[i])
    return rows[best], float(scores[best])
