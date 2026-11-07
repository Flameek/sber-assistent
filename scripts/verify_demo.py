"""Run against the freshly started Compose stack; uses only synthetic training data."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

URL = "http://127.0.0.1:8501"
ROOT = Path(__file__).resolve().parents[1]
ACCESS = "Как стажёру запросить доступ к реестру инцидентов?"
CLASSIFY = "Как классифицировать инцидент по влиянию?"
MARKER = "УЧ-ИБ-7"

def run(page):
    page.goto(URL)
    def role(name):
        page.get_by_role("combobox").click()
        page.get_by_role("option", name=name, exact=True).click()
    def ask(q):
        box = page.get_by_role("textbox", name="Вопрос по инструкциям")
        box.fill(q)
        box.press("Enter")
        page.get_by_role("button", name="Найти ответ", exact=True).click()
    def open_source(ref):
        page.get_by_role("button", name="Открыть раздел инструкции").click()
        page.wait_for_function("r => new URL(location.href).searchParams.get('source') === r", arg=ref)
    def answer():
        return page.get_by_test_id("stText").first
    def check(msg):
        print("PASS:", msg, flush=True)
    role("Стажёр ИБ")
    ask(ACCESS)
    open_source("access@2#request")
    expect(page.get_by_text("Версия 2 · § request", exact=True)).to_be_visible()
    check("актуальная инструкция и ссылка на версию 2")

    ask(CLASSIFY)
    expect(answer()).to_contain_text(MARKER)
    open_source("triage@1#classify")
    role("Стажёр поддержки")
    expect(page.get_by_text("Раздел недоступен.", exact=True)).to_be_visible()
    ask(CLASSIFY)
    expect(answer()).to_contain_text("нет подтверждённого ответа")
    expect(page.get_by_text(MARKER, exact=False)).to_have_count(0)
    check("закрытый раздел и повторный запрос не раскрывают текст поддержке")

    page.goto(URL)
    role("Стажёр ИБ")
    ask("Какой срок эскалации критического инцидента?")
    expect(answer()).to_contain_text("Передайте вопрос тимлиду")
    expect(page.get_by_role("button", name="Открыть раздел инструкции")).to_have_count(0)
    check("равноприоритетный конфликт передаётся тимлиду")

    ask("Как оформить командировку?")
    expect(answer()).to_contain_text("нет подтверждённого ответа")
    expect(page.get_by_role("button", name="Открыть раздел инструкции")).to_have_count(0)
    check("при отсутствии материала нет выдуманного ответа")

    page.get_by_text("Предложить учебную инструкцию", exact=True).click()
    page.locator('input[type=file]').set_input_files(str(ROOT/"data/update-example.json"))
    page.get_by_role("button", name="Отправить на проверку").click()
    expect(page.get_by_text("передано тимлиду", exact=False)).to_be_visible()
    ask(ACCESS)
    open_source("access@2#request")
    expect(answer()).not_to_contain_text("КУРС-03")
    role("Тимлид ИБ (демо)")
    page.get_by_text("№1: Доступ к реестру инцидентов, версия 3", exact=True).click()
    page.get_by_role("button", name="Утвердить", exact=True).click()
    expect(page.get_by_role("button", name="Утвердить", exact=True)).to_have_count(0)
    role("Стажёр ИБ")
    ask(ACCESS)
    expect(answer()).to_contain_text("КУРС-03")
    open_source("access@3#request")
    expect(page.get_by_text("Версия 3 · § request", exact=True)).to_be_visible()
    check("до утверждения действует v2; после него стажёр получает v3 и новый источник")
    # A new session reads SQLite and the updated Elasticsearch index.
    page.goto(URL)
    ask(ACCESS)
    expect(answer()).to_contain_text("КУРС-03")
    check("опубликованное обновление доступно в новой сессии")

if __name__ == "__main__":
    with sync_playwright() as p:
        with p.chromium.launch(channel="chrome") as browser:
            page = browser.new_page(locale="ru-RU")
            page.set_default_timeout(20000)
            expect.set_options(timeout=15000)
            run(page)
