"""Explicit vocabulary for the teaching scenario, not a language model.

Query topics describe an operation, not just a shared noun. Unsupported operations
remain separate so that 'revoke access' cannot retrieve 'request read access'.
"""
import re

TOPICS = {
    "access-read": "Получение доступа на чтение",
    "access-admin": "Администраторский доступ",
    "access-write": "Доступ на изменение данных",
    "access-revoke": "Отзыв доступа",
    "access-restore": "Восстановление доступа",
    "access-without-approval": "Доступ без согласования",
    "account-create": "Создание учётной записи",
    "password-reset": "Восстановление пароля",
    "incident-create": "Регистрация инцидента",
    "incident-delete": "Удаление инцидента",
    "incident-classify": "Классификация инцидента",
    "incident-escalate": "Эскалация инцидента",
    "request-status": "Проверка статуса заявки",
    "request-edit": "Изменение заявки или её статуса",
    "request-rejected": "Действия при отклонении заявки",
    "request-deadline": "Срок обработки заявки",
    "access-problem": "Ошибка при работе с доступом",
}
LEGACY_TOPICS = {
    "access": "access-read", "register": "incident-create",
    "triage": "incident-classify", "escalation": "incident-escalate",
    "status": "request-status",
}


def normalize(text):
    return " ".join(text.casefold().replace("ё", "е").split())


def row_topic(row):
    # Existing SQLite databases remain readable without rewriting published data.
    return row.get("topic") or LEGACY_TOPICS.get(row["rule"])


def query_topics(question):
    """Return ordered operations. More specific access types override read access.

    This is intentionally a bounded vocabulary. New systems/operations require
    extending this module and adding independently worded regression questions.
    """
    q = normalize(question)
    # Only one teaching system is covered. Do not silently substitute it for
    # another explicitly named target such as mail, VPN or SIEM.
    targets = re.findall(r"\b(?:в|во|к|ко)\s+([a-zа-я][a-zа-я0-9_-]*)", q)
    allowed_target = r"реестр.*|учебн.*|карточк.*|раздел.*|заявк.*|портал.*|систем.*|инструкц.*|отдел.*|подраздел.*|наставник.*|руководител.*|дежурн.*|течени.*|согласован.*"
    if any(not re.fullmatch(allowed_target, target) for target in targets):
        return []
    if re.search(r"\b(?:vpn|siem|dlp|почт\w*|jira|confluence|sbercrm)\b", q):
        return []
    found = []

    def add(topic, pattern):
        match = re.search(pattern, q)
        if match:
            found.append((match.start(), topic))
            return True
        return False

    access = bool(re.search(r"доступ|прав[аоыу]?\b", q))
    request = bool(re.search(r"заявк|заявок", q))
    incident = bool(re.search(r"инцидент|карточк", q))
    if (access or request) and re.search(r"сколько|когда|срок", q) and not re.search(r"эскалац|эскалир", q):
        return ["request-deadline"]
    if access and re.search(r"ошибк|не работает|не открыва|не могу|недоступ", q):
        return ["access-problem"]
    if re.search(r"парол", q):
        add("password-reset", r"парол")
    if re.search(r"учетн.*запис|аккаунт", q):
        add("account-create", r"учетн|аккаунт")
    if request and re.search(r"отклон|отказал|отказан", q):
        # A view-status procedure cannot explain what to do after rejection.
        add("request-rejected", r"отклон|отказал|отказан")
    elif request and re.search(r"измен|помен|исправ|редакт", q):
        add("request-edit", r"измен|помен|исправ|редакт")
    elif request:
        add("request-status", r"статус|состоян|этап|отслед")

    if incident:
        add("incident-delete", r"удал|стереть|стира")
        add("incident-create", r"зарегистр|регистрир|регистрац|созда|завест|новая карточка")
    add("incident-classify", r"классифиц|классификац|категори|влияни")
    add("incident-escalate", r"эскалац|эскалир")

    if access:
        specific = False
        for topic, pattern in (
            ("access-revoke", r"отозв|отзыв|лишить|заблок|отключ|удал.*доступ"),
            ("access-restore", r"восстанов|разблок"),
            ("access-admin", r"администратор|админ\b"),
            ("access-write", r"запис[ьи]|редактир|изменени.*данн|полны[йех].*прав"),
            ("access-without-approval", r"без\s+(?:заявк|согласован|одобрен)|обойти.*согласован"),
        ):
            specific = add(topic, pattern) or specific
        explicit_request = re.search(r"получ|запрос|оформ|кому.*отправ|куда.*отправ|чтени", q)
        if not specific and (not found or explicit_request and not request):
            add("access-read", r"доступ|прав[аоыу]?\b")
        elif not specific and not any(t.startswith("request-") for _, t in found):
            add("access-read", r"доступ|прав[аоыу]?\b")
        # Compound: 'получить доступ, затем проверить статус заявки'.
        elif not specific and explicit_request and re.search(r"[,;]|\bзатем\b|\bпотом\b|\bи\b", q):
            add("access-read", r"доступ|прав[аоыу]?\b")

    return list(dict.fromkeys(topic for _, topic in sorted(found)))
