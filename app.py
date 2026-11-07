import streamlit as st
from kb.corpus import chunks, ROLES
from kb.store import Store
import json
from kb.backend import backend
from kb.service import Service

st.set_page_config(page_title="Ассистент базы знаний",page_icon="📘")
st.title("Ассистент базы знаний")
st.caption("Учебный реестр инцидентов · материалы условного банка")
profiles={**ROLES,"lead":"Тимлид ИБ (демо)"}
actor=st.sidebar.selectbox("Демонстрационный профиль",["support","ib","lead"],format_func=profiles.get)
role="ib" if actor=="lead" else actor
st.sidebar.caption("Переключатель для локального показа на синтетических данных. Это не вход в корпоративную систему.")
@st.cache_resource
def engine():return backend()
store=Store()
service=Service(chunks(store.published()),engine())
q=st.text_input("Вопрос по инструкциям","Как стажёру запросить доступ к реестру инцидентов?")
if st.button("Найти ответ") or st.session_state.get("last") == (role,q):
    st.session_state["last"]=(role,q)
    try:
        result=service.ask(role,q);st.text(result["text"])
        if result["source"]:
            if st.button("Открыть раздел инструкции"):
                st.query_params["source"]=result["source"]
    except (OSError, RuntimeError, ValueError):
        st.error("Поисковый сервис недоступен. Проверьте состояние Elasticsearch.")
ref=st.query_params.get("source")
if ref:
    try:
        row=service.source(role,ref)
        if row:
            st.subheader(row["title"]); st.caption(f"Версия {row['version']} · § {row['key']}");st.text(row["text"])
        else:st.info("Раздел недоступен.")
    except (OSError,RuntimeError,ValueError):st.error("Поисковый сервис недоступен.")

with st.expander("Предложить учебную инструкцию"):
    st.caption("Загрузите одну инструкцию в JSON по образцу из data/update-example.json. Она станет доступна только после утверждения.")
    upload=st.file_uploader("Новая версия инструкции",type=["json"])
    if st.button("Отправить на проверку",disabled=not upload):
        try:
            if upload.size>200000:raise ValueError("Файл больше 200 КБ")
            n=store.propose(json.loads(upload.getvalue()),actor)
            st.success(f"Предложение №{n} передано тимлиду.")
        except (ValueError,TypeError,UnicodeError) as e:st.error(str(e))
if actor=="lead":
    st.subheader("На подтверждении")
    for n,d in store.pending(actor):
        with st.expander(f"№{n}: {d['title']}, версия {d['version']}"):
            st.text("Роли: "+", ".join(d["roles"])+f" · приоритет: {d['priority']} · правило: "+d["rule"])
            for sec in d["sections"]:st.text(sec["key"]+" · "+sec["text"])
            if st.button("Утвердить",key=f"approve{n}"):
                try:store.approve(n,actor);st.rerun()
                except ValueError as e:st.error(str(e))
