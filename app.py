import json

import streamlit as st

from kb.answer import as_markdown
from kb.backend import backend
from kb.corpus import LEVEL, ROLES, chunks
from kb.service import Service
from kb.store import Store

st.set_page_config(page_title="Ассистент базы знаний", page_icon="📘")
st.markdown(
    """<style>
    .block-container {max-width: 820px; padding-top: 2.5rem;}
    .st-key-answer, .st-key-source {background: #111a2c;}
    </style>""",
    unsafe_allow_html=True,
)


@st.cache_resource
def engine():
    return backend()


store = Store()
service = Service(chunks(store.published()), engine())
@st.cache_resource(show_spinner=False)
def warm_up(ranker):
    """Загрузить модель эмбеддингов заранее, один раз за время работы приложения."""
    if ranker == "hybrid":
        from kb.embeddings import encode_query
        encode_query("прогрев")
    return True


with st.spinner("Загружаю модель поиска… Это нужно только при первом запуске."):
    warm_up(service.ranker)
# ---------- Боковая панель: кто спрашивает ----------
with st.sidebar:
    st.markdown("### 👤 Профиль")
    actor = st.selectbox("Демонстрационный профиль", list(ROLES), format_func=ROLES.get)
    role = actor
    level = LEVEL[role] + 1
    st.progress(level / len(ROLES), text=f"Уровень доступа: {level} из {len(ROLES)}")
    try:
        st.caption(f"Доступно инструкций: {len(service.visible(role))}")
    except (OSError, RuntimeError, ValueError):
        st.caption("Доступно инструкций: поиск недоступен")
    st.divider()
    if service.ranker == "hybrid":
        from kb.embeddings import MODEL_NAME
        st.caption(f"Поиск: гибрид TF-IDF + эмбеддинги ({MODEL_NAME})")
    else:
        st.caption("Поиск: TF-IDF с лемматизацией")
    st.caption("Переключатель для локального показа на синтетических данных. Это не вход в корпоративную систему.")

# ---------- Вопрос ----------
st.title("📘 Ассистент базы знаний")
st.caption("Учебный реестр инцидентов · материалы условного банка")
q = st.text_input("Вопрос по инструкциям", "Как стажёру запросить доступ к реестру инцидентов?")
st.caption("Например: «Как зарегистрировать новый инцидент?», «Мою заявку вернули на доработку, что делать?»")

if st.button("Найти ответ", type="primary") or st.session_state.get("last") == (role, q):
    st.session_state["last"] = (role, q)
    try:
        with st.spinner("Ищу ответ в инструкциях…"):
            result = service.ask(role, q)
        with st.container(border=True, key="answer"):
            if result["kind"] == "answer":
                st.markdown(f"#### ✅ {result['title']}")
                st.markdown(as_markdown(result))
                st.caption(f"📄 Версия {result['version']} · 👤 Ответственный: {result['contact']}")
            elif result["kind"] == "conflict":
                st.markdown("#### ⚖️ Инструкции расходятся")
                st.warning(result["text"])
            else:
                st.markdown("#### 🔍 Ответ не найден")
                st.warning(result["text"])
        if result["source"]:
            if st.button("Открыть раздел инструкции"):
                st.query_params["source"] = result["source"]
    except (OSError, RuntimeError, ValueError):
        st.error("Поисковый сервис недоступен. Проверьте состояние Elasticsearch.")

# ---------- Раздел инструкции по ссылке ----------
ref = st.query_params.get("source")
if ref:
    try:
        row = service.source(role, ref)
        if row:
            with st.container(border=True, key="source"):
                st.subheader(row["title"])
                st.caption(f"Версия {row['version']} · § {row['key']}")
                st.markdown(row["text"])
        else:
            st.info("Раздел недоступен.")
    except (OSError, RuntimeError, ValueError):
        st.error("Поисковый сервис недоступен.")

# ---------- Новые инструкции ----------
st.write("")
with st.expander("Предложить учебную инструкцию"):
    st.caption("Загрузите одну инструкцию в JSON по образцу из data/update-example.json. Она станет доступна только после утверждения.")
    upload = st.file_uploader("Новая версия инструкции", type=["json"])
    if st.button("Отправить на проверку", disabled=not upload):
        try:
            if upload.size > 200000:
                raise ValueError("Файл больше 200 КБ")
            n = store.propose(json.loads(upload.getvalue()), actor)
            st.success(f"Предложение №{n} передано тимлиду.")
        except (ValueError, TypeError, UnicodeError) as e:
            st.error(str(e))

if actor == "lead":
    st.subheader("На подтверждении")
    pending = store.pending(actor)
    if not pending:
        st.caption("Новых предложений нет.")
    for n, d in pending:
        with st.expander(f"№{n}: {d['title']}, версия {d['version']}"):
            st.text("Роли: " + ", ".join(d["roles"]) + f" · приоритет: {d['priority']} · правило: " + d["rule"])
            for sec in d["sections"]:
                st.text(sec["key"] + " · " + sec["text"])
            if st.button("Утвердить", key=f"approve{n}"):
                try:
                    store.approve(n, actor)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))