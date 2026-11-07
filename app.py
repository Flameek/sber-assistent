"""Streamlit UI for a model-backed, access-scoped internal knowledge assistant."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from kb.backend import backend
from kb.corpus import ROLES, chunks
from kb.importer import import_document
from kb.llm import ModelClient, ModelConfig, ModelError
from kb.rag import Assistant
from kb.store import Store
from kb.users import Users

load_dotenv(Path(__file__).with_name('.env'), override=False)
st.set_page_config(page_title='Ассистент ИБ', page_icon='📘', layout='wide')
PROFILES = {**ROLES, 'lead': 'Тимлид ИБ'}
AREAS = {'реестр': 'Реестр инцидентов', 'siem': 'Учебная SIEM', 'vpn': 'Учебный VPN'}
store = Store()
users = Users(store.path)
demo = os.getenv('KB_DEMO_MODE', 'false').lower() == 'true'

if demo:
    profile = st.sidebar.selectbox('Учебный профиль', ['support', 'ib', 'lead'], format_func=PROFILES.get)
    username = 'demo-' + profile
    st.sidebar.caption('Демонстрационный режим · только вымышленные данные')
else:
    identity = users.session(st.session_state.get('auth_token'))
    if identity is None:
        st.title('Вход в базу знаний')
        st.caption('Ассистент для сотрудников учебного банка')
        with st.form('login'):
            login = st.text_input('Логин', max_chars=48)
            password = st.text_input('Пароль', type='password', max_chars=256)
            submitted = st.form_submit_button('Войти')
        if submitted:
            token = users.login(login, password)
            if token:
                st.session_state.clear()
                st.session_state['auth_token'] = token
                st.rerun()
            else:
                st.error('Неверные данные для входа.')
        st.info('Первого пользователя создаёт администратор командой python -m kb.users create LOGIN --profile lead.')
        st.stop()
    username, profile = identity['username'], identity['profile']
    st.sidebar.text(username)
    st.sidebar.caption(PROFILES[profile])
    if st.sidebar.button('Выйти'):
        users.logout(st.session_state.get('auth_token'))
        st.session_state.clear()
        st.rerun()
reader = 'ib' if profile == 'lead' else profile
all_rows = chunks(store.published())
areas = sorted({r['area'] for r in all_rows if reader in r['roles']}, key=lambda value: (value != 'реестр', value))
if not areas:
    st.info('Для вашего профиля нет опубликованных инструкций.')
    st.stop()
area = st.sidebar.selectbox('Система', areas, format_func=lambda value: AREAS.get(value, value))
if st.session_state.get('active_area') not in (None, area):
    st.query_params.pop('source', None)
st.session_state['active_area'] = area
mode = st.sidebar.radio('Режим ответа', ['ИИ-ответ', 'Поиск по инструкциям'])

@st.cache_resource
def engine():
    return backend()

@st.cache_resource
def model_client(config):
    return ModelClient(config)

try:
    config = ModelConfig.from_env()
    assistant = Assistant(store, engine(), model_client(config) if mode == 'ИИ-ответ' else None,
                          search_only=mode != 'ИИ-ответ')
except ModelError as error:
    st.error(str(error))
    st.stop()

scope = (username, profile, mode, *assistant.scope_key(reader, area))
if st.session_state.get('scope') != scope:
    st.session_state['scope'] = scope
    st.session_state['messages'] = []
    st.session_state.pop('draft', None)
if st.sidebar.button('Новый диалог'):
    st.session_state['messages'] = []
    st.query_params.clear()
    st.rerun()
st.sidebar.divider()
st.sidebar.caption('Поиск без вызова модели' if mode != 'ИИ-ответ' else
                   'Внешняя модель: разрешена' if config.provider == 'gigachat' else 'Обработка запросов в локальном контуре')
st.title('Ассистент базы знаний ИБ')
st.caption('Учебный банк · ответы по утверждённым инструкциям · ' + AREAS.get(area, area))

def show_answer(result, key):
    if result['kind'] == 'partial':
        st.warning('Ответ найден на часть вопроса. Для остальных действий нужно уточнение или обращение к ответственному.')
    elif result['kind'] in ('conflict', 'clarify'):
        st.info('Нужна проверка или уточнение.')
    st.text(result['text'])
    for index, source in enumerate(result['sources']):
        try:
            available = assistant.source(reader, area, source['ref'])
        except (OSError, RuntimeError, ValueError):
            st.warning('Источник сейчас недоступен: проверьте поисковый сервис.')
            continue
        if available is None:
            continue
        with st.expander(source['title'] + ' · ' + source['ref']):
            st.caption(f"Версия {source['version']} · приоритет {source['priority']}")
            st.text(source.get('quote', source['text']))
            if st.button('Открыть раздел инструкции', key=f'{key}-src-{index}'):
                st.query_params['source'] = source['ref']
    if result.get('explanation'):
        with st.expander('Почему выбран этот ответ'):
            st.text(result['explanation'])
    if result.get('generated'):
        st.caption(f"Модель: {result['model']} · {result['elapsed_ms']/1000:.1f} с")

names = ['Помощник', 'Документы'] + (['Согласование'] if profile == 'lead' else [])
tabs = st.tabs(names)
with tabs[0]:
    if not st.session_state['messages']:
        st.write('Задайте вопрос о выбранной системе. Если инструкции недостаточно, ассистент сообщит об этом.')
        examples = {'реестр': ['Как получить доступ к реестру?', 'Как зарегистрировать инцидент и проверить статус заявки?'],
                    'siem': ['Как войти в учебную SIEM?', 'Как разобрать событие?'],
                    'vpn': ['Как подключиться к учебному VPN?', 'Что делать при ошибке сертификата?']}
        for example in examples.get(area, []):
            st.caption('Например: ' + example)
    for number, item in enumerate(st.session_state['messages']):
        with st.chat_message('user'):
            st.text(item['question'])
        with st.chat_message('assistant'):
            show_answer(item['result'], f'history-{number}')
    question = st.chat_input('Вопрос по инструкциям', max_chars=2000)
    if question:
        with st.chat_message('user'):
            st.text(question)
        with st.chat_message('assistant'):
            try:
                with st.spinner('Ищу инструкции и готовлю ответ…'):
                    result = assistant.ask(reader, question, area, st.session_state['messages'][-6:])
                st.session_state['messages'].append({'question': question, 'result': result})
                st.session_state['messages'] = st.session_state['messages'][-20:]
                st.rerun()
            except ModelError as error:
                st.error(str(error))
                st.info('Для локального режима запустите Ollama и загрузите модель из инструкции README. Автоматической подмены ответа модели нет.')
            except (OSError, RuntimeError, ValueError):
                st.error('Не удалось обработать вопрос. Проверьте поисковый сервис и настройки.')

ref = st.query_params.get('source')
if ref:
    try:
        row = assistant.source(reader, area, ref)
        with st.expander('Открытый источник', expanded=True):
            if row:
                st.subheader(row['title'])
                st.caption(f"{row['ref']} · версия {row['version']} · ответственный: {row['contact']}")
                st.text(row['text'])
            else:
                st.info('Раздел недоступен.')
    except (OSError, RuntimeError, ValueError):
        st.error('Поисковый сервис недоступен.')

with tabs[1]:
    st.subheader('Доступные инструкции')
    visible = [r for r in all_rows if reader in r['roles'] and r['area'] == area]
    records = {(r['id'], r['version']): r for r in visible}
    st.dataframe([{'Документ': r['title'], 'Версия': r['version'], 'Приоритет': r['priority'],
                   'Ответственный': r['contact']} for r in records.values()], hide_index=True, width='stretch')
    st.subheader('Предложить инструкцию')
    st.caption('PDF, DOCX, TXT, MD или JSON. Публикация происходит после проверки тимлидом.')
    upload = st.file_uploader('Файл инструкции', type=['pdf', 'docx', 'txt', 'md', 'json'], key='upload-' + username)
    with st.form('proposal'):
        title = st.text_input('Название', max_chars=180)
        ident = st.text_input('Идентификатор документа', 'new-instruction', max_chars=48)
        doc_area = st.text_input('Система (идентификатор)', area, max_chars=64)
        contact = st.text_input('Ответственный', 'Служба сопровождения учебной системы', max_chars=180)
        left, right = st.columns(2)
        version = left.number_input('Версия', min_value=1, max_value=100000, value=1)
        priority = right.number_input('Приоритет', min_value=1, max_value=100, value=30)
        roles = st.multiselect('Кому доступно', list(ROLES), default=[reader], format_func=ROLES.get)
        topic = st.text_input('Тема/операция', ident, max_chars=48, help='Одна тема обозначает одну операцию. Для JSON используются поля из файла.')
        proposed = st.form_submit_button('Отправить на проверку')
    if proposed:
        try:
            if upload is None:
                raise ValueError('Выберите файл')
            metadata = {'id': ident, 'rule': topic, 'topic': topic, 'version': int(version), 'priority': int(priority),
                        'title': title, 'contact': contact, 'roles': roles, 'area': doc_area}
            document = import_document(upload.name, upload.getvalue(), metadata)
            n = store.propose(document, profile, author=username)
            st.success(f'Предложение №{n} передано тимлиду. До утверждения ответы не меняются.')
        except (ValueError, TypeError, UnicodeError) as error:
            st.error(str(error))

if profile == 'lead':
    with tabs[2]:
        st.subheader('На подтверждении')
        reviews = store.reviews(profile)
        pending = [r for r in reviews if r['state'] == 'pending']
        if not pending:
            st.info('Новых предложений нет.')
        for review in pending:
            n, doc = review['n'], review['document']
            with st.expander(f"№{n}: {doc['title']}, версия {doc['version']}"):
                st.caption(f"Автор: {review['author']} · система: {doc['area']} · приоритет: {doc['priority']}")
                st.text('Права: ' + ', '.join(doc['roles']))
                related = [r for r in all_rows if r['area'] == doc['area'] and
                           (r['rule'] == doc['rule'] or r.get('topic') in {s.get('topic') for s in doc['sections']})]
                if related:
                    st.info('Проверьте согласованность с действующими источниками: ' + ', '.join(dict.fromkeys(r['ref'] for r in related)))
                for section in doc['sections']:
                    st.text(section['key'] + ' · ' + section['text'])
                    if section.get('facts'):
                        st.json(section['facts'])
                if st.button('Утвердить', key=f'approve-{n}'):
                    try:
                        store.approve(n, profile, reviewer=username)
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
                reason = st.text_area('Причина отклонения', key=f'reason-{n}', max_chars=1000)
                if st.button('Отклонить', key=f'reject-{n}'):
                    try:
                        store.reject(n, profile, reason, reviewer=username)
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
        with st.expander('История решений'):
            for review in reviews:
                if review['state'] != 'pending':
                    st.text(f"№{review['n']} · {review['document']['title']} · {review['state']}")
                    st.caption(f"Автор: {review['author']} · Проверил: {review['reviewer']}")
                    if review['comment']:
                        st.text(review['comment'])
