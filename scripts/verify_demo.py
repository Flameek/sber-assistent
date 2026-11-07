"""Browser acceptance: fast retrieval flows plus optional real-model checks."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv('KB_DEMO_URL', 'http://127.0.0.1:8501')


def run(page):
    page.goto(URL)
    sidebar = page.get_by_test_id('stSidebar')
    def profile(name):
        sidebar.get_by_role('combobox').nth(0).click()
        page.get_by_role('option', name=name, exact=True).click()
    def system(name):
        sidebar.get_by_role('combobox').nth(1).click()
        page.get_by_role('option', name=name, exact=True).click()
    def mode(name):
        sidebar.get_by_text(name, exact=True).click()
    def ask(question):
        page.get_by_role('tab', name='Помощник', exact=True).click()
        box = page.get_by_placeholder('Вопрос по инструкциям')
        box.fill(question)
        box.press('Enter')
    def latest():
        return page.get_by_test_id('stChatMessage').last
    def check(message):
        print('PASS:', message, flush=True)
    def propose(doc):
        page.get_by_role('tab', name='Документы', exact=True).click()
        page.locator('input[type=file]').set_input_files({'name':'instruction.json','mimeType':'application/json',
                                                        'buffer':json.dumps(doc,ensure_ascii=False).encode()})
        page.get_by_role('button', name='Отправить на проверку', exact=True).click()
        expect(page.get_by_text('передано тимлиду', exact=False)).to_be_visible()

    mode('Поиск по инструкциям')
    profile('Стажёр ИБ')
    ask('Как получить доступ к реестру?')
    expect(latest()).to_contain_text('Доступ на чтение')
    latest().get_by_text('Почему выбран этот ответ', exact=True).click()
    expect(latest()).to_contain_text('приоритет 30')
    check('актуальная инструкция и объяснение приоритета')

    ask('Как классифицировать инцидент по влиянию?')
    expect(latest()).to_contain_text('УЧ-ИБ-7')
    latest().get_by_text('Первичная классификация инцидента · triage@1#classify', exact=True).click()
    latest().get_by_role('button', name='Открыть раздел инструкции', exact=True).click()
    page.wait_for_function("new URL(location.href).searchParams.get('source')==='triage@1#classify'")
    profile('Стажёр поддержки')
    expect(page.get_by_text('Раздел недоступен.', exact=True)).to_be_visible()
    expect(page.get_by_text('УЧ-ИБ-7', exact=False)).to_have_count(0)
    check('смена роли очищает историю и запрещает закрытый источник')

    ask('Как отозвать доступ к реестру?')
    expect(latest()).to_contain_text('нет подтверждённого ответа')
    ask('Как получить доступ администратора к реестру?')
    expect(latest()).to_contain_text('нет подтверждённого ответа')
    check('другие типы доступа не подменяются инструкцией чтения')

    profile('Стажёр ИБ')
    ask('Как зарегистрировать инцидент и проверить статус заявки?')
    expect(latest()).to_contain_text('наблюдаемый симптом')
    expect(latest()).to_contain_text('Состояние')
    expect(latest()).to_contain_text('create@1#new')
    expect(latest()).to_contain_text('status@1#check')
    check('составной вопрос и два источника')

    ask('Какой срок эскалации критического инцидента?')
    expect(latest()).to_contain_text('тимлиду')
    ask('Как оформить командировку?')
    expect(latest()).to_contain_text('нет подтверждённого ответа')
    check('конфликт и отсутствие ответа')

    updated = json.loads((ROOT/'data/update-example.json').read_text(encoding='utf-8'))
    propose(updated)
    ask('Как получить доступ к реестру?')
    expect(latest()).not_to_contain_text('КУРС-03')
    profile('Тимлид ИБ')
    page.get_by_role('tab', name='Согласование', exact=True).click()
    page.get_by_text('№1: Доступ к реестру инцидентов, версия 3', exact=True).click()
    page.get_by_role('button', name='Утвердить', exact=True).click()
    profile('Стажёр ИБ')
    ask('Как получить доступ к реестру?')
    expect(latest()).to_contain_text('КУРС-03')
    check('публикация новой версии только после утверждения')

    rejected = json.loads(json.dumps(updated))
    rejected['version'] = 4
    rejected['sections'][0]['text'] = 'Для доступа укажите код КУРС-04.'
    propose(rejected)
    profile('Тимлид ИБ')
    page.get_by_role('tab', name='Согласование', exact=True).click()
    page.get_by_text('№2: Доступ к реестру инцидентов, версия 4', exact=True).click()
    page.get_by_role('textbox', name='Причина отклонения', exact=True).fill('Уточнить порядок согласования')
    page.get_by_role('button', name='Отклонить', exact=True).click()
    page.get_by_text('История решений', exact=True).click()
    expect(page.get_by_text('Уточнить порядок согласования', exact=True)).to_be_visible()
    profile('Стажёр ИБ')
    ask('Как получить доступ к реестру?')
    expect(latest()).to_contain_text('КУРС-03')
    expect(latest()).not_to_contain_text('КУРС-04')
    check('отклонение с причиной сохраняет прежнюю инструкцию')

    if os.getenv('KB_VERIFY_LLM') == '1':
        mode('ИИ-ответ')
        ask('Как получить доступ к реестру?')
        expect(latest()).to_contain_text('КУРС-03', timeout=180000)
        expect(latest()).to_contain_text('Модель:', timeout=180000)
        check('реальная LLM отвечает по новой версии с источником')
        system('Учебная SIEM')
        ask('Как разобрать событие в SIEM?')
        expect(latest()).to_contain_text('siem-alert@1#procedure', timeout=180000)
        expect(latest()).not_to_contain_text('siem-login@1#procedure')
        check('реальная LLM различает разбор события и вход в SIEM')
        page.screenshot(path=str(ROOT/'docs/assistant-demo.png'), full_page=True)


if __name__ == '__main__':
    with sync_playwright() as p:
        options = {'executable_path':os.environ['KB_BROWSER_EXECUTABLE']} if os.getenv('KB_BROWSER_EXECUTABLE') else {'channel':'chrome'}
        with p.chromium.launch(**options) as browser:
            page=browser.new_page(locale='ru-RU', viewport={'width':1440,'height':1000})
            page.set_default_timeout(20000)
            expect.set_options(timeout=20000)
            run(page)
