"""Пробный запуск эмбеддингов: насколько близки вопросы и разделы инструкций."""
from sentence_transformers import SentenceTransformer

from kb.corpus import chunks, seed

model = SentenceTransformer("intfloat/multilingual-e5-small")
rows = chunks(seed())

# Модели семейства e5 обучены с приставками: "passage: " для текста, "query: " для вопроса.
passages = ["passage: " + r["title"] + ". " + r["text"] for r in rows]
questions = [
    "Как получить пропуск в реестр инцидентов?",   # S01: синоним «пропуск» = «доступ»
    "Как зафиксировать новый инцидент?",           # S17: «зафиксировать» = «зарегистрировать»
    "Как добавить инцидент в реестр?",             # S16
    "Как стажёру запросить доступ к реестру инцидентов?",  # контроль: это TF-IDF и так находит
    "Какой график у дежурной смены?",              # S40: ловушка, ответа нет
    "Где находится столовая?",                     # S36: совсем не по теме
]

# normalize_embeddings=True: векторы длины 1, тогда скалярное произведение = косинусная близость.
P = model.encode(passages, normalize_embeddings=True)
Q = model.encode(["query: " + q for q in questions], normalize_embeddings=True)
scores = Q @ P.T  # таблица близостей: строка — вопрос, столбец — раздел

for question, row in zip(questions, scores):
    print(question)
    for i in row.argsort()[::-1][:3]:  # три самых близких раздела
        print(f"    {row[i]:.3f}  {rows[i]['ref']}")