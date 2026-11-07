"""Regenerate committed synthetic demo materials, not the app's live database.

Optional developer dependencies: reportlab, python-docx. DejaVu Sans font location
can be supplied with DEMO_FONT. Application users do not need to run this script.
"""
from copy import deepcopy
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DISCLAIMER = 'Учебный материал БВТ2506. Все названия, значения и процедуры вымышлены; это не инструкция Сбера.'

CASES = [
    {
        'file': '02-upload/01-vpn-telemetry.txt',
        'title': 'Калибровка телеметрии учебного VPN',
        'id': 'demo-vpn-telemetry', 'topic': 'vpn-telemetry-calibration',
        'roles': ['ib', 'support'], 'question': 'Как выполнить калибровку телеметрии?',
        'marker': 'ТЕЛЕМЕТРИЯ-21',
        'text': 'Чтобы выполнить калибровку телеметрии, откройте учебную диагностическую панель. Выберите «Телеметрия → Калибровка». Укажите учебную метку ТЕЛЕМЕТРИЯ-21 и нажмите «Проверить». Сохраните номер диагностического протокола и передайте его наставнику.',
    },
    {
        'file': '02-upload/02-vpn-route-selftest.md',
        'title': 'Самодиагностика маршрутизации учебного VPN',
        'id': 'demo-vpn-route-selftest', 'topic': 'vpn-route-selftest',
        'roles': ['ib', 'support'], 'question': 'Как выполнить самодиагностику маршрутизации?',
        'marker': 'МАРШРУТ-26',
        'text': 'Для самодиагностики маршрутизации откройте учебную диагностическую панель. Выберите «Маршрутизация → Самодиагностика». Введите учебный профиль МАРШРУТ-26 и нажмите «Запустить». Если проверка завершилась ошибкой, сохраните номер протокола и обратитесь в службу сетевой поддержки.',
    },
    {
        'file': '02-upload/03-vpn-connector-attestation.docx',
        'title': 'Аттестация коннектора учебного VPN',
        'id': 'demo-vpn-connector', 'topic': 'vpn-connector-attestation',
        'roles': ['ib'], 'question': 'Как выполнить аттестацию коннектора?',
        'marker': 'КОННЕКТОР-32',
        'text': 'Для аттестации коннектора откройте учебный диагностический модуль. Выберите «Коннектор → Аттестация» и укажите учебный сценарий КОННЕКТОР-32. Нажмите «Проверить целостность». После завершения сохраните протокол и передайте его наставнику ИБ.',
    },
    {
        'file': '02-upload/04-vpn-gateway-fingerprint.pdf',
        'title': 'Сверка отпечатка шлюза учебного VPN',
        'id': 'demo-vpn-gateway', 'topic': 'vpn-gateway-fingerprint',
        'roles': ['ib', 'support'], 'question': 'Как сверить отпечаток шлюза?',
        'marker': 'ШЛЮЗ-43',
        'text': 'Для сверки отпечатка шлюза откройте учебное окно «Параметры шлюза». Сравните показанное учебное значение с меткой ШЛЮЗ-43. Если значения совпали, сохраните результат проверки в учебном протоколе. Если значения различаются, остановите проверку и передайте вопрос в службу сетевой поддержки.',
    },
    {
        'file': '02-upload/05-vpn-diagnostics-archive.json',
        'title': 'Архивация протокола диагностики учебного VPN',
        'id': 'demo-vpn-archive', 'topic': 'vpn-diagnostics-archive',
        'roles': ['ib', 'support'], 'question': 'Как выполнить архивацию протокола диагностики?',
        'marker': 'АРХИВ-54',
        'text': 'Для архивации протокола диагностики откройте учебный раздел «Диагностика → Протоколы». Выберите протокол и нажмите «Архивировать». Укажите учебную метку АРХИВ-54 и сохраните номер архивной записи. Архивная запись остаётся в учебном внутреннем хранилище.',
    },
]


def metadata(case):
    return {'id': case['id'], 'rule': case['topic'], 'topic': case['topic'],
            'version': 1, 'priority': 30, 'title': case['title'],
            'contact': 'Служба сетевой поддержки', 'roles': case['roles'], 'area': 'vpn'}


def structured(case):
    value = metadata(case)
    topic = value.pop('topic')
    value['sections'] = [{'key': 'procedure', 'topic': topic, 'text': case['text']}]
    return value


def write_pdf(path, title, text):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    candidates = [Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), Path('/usr/share/fonts/TTF/DejaVuSans.ttf')]
    font_path = Path(os.environ['DEMO_FONT']) if os.getenv('DEMO_FONT') else next((p for p in candidates if p.is_file()), candidates[0])
    if not font_path.is_file():
        raise SystemExit('Укажите путь к шрифту DejaVu Sans через DEMO_FONT')
    pdfmetrics.registerFont(TTFont('DemoDejaVu', str(font_path)))
    title_style = ParagraphStyle('Title', fontName='DemoDejaVu', fontSize=16, leading=22,
                                 textColor=colors.HexColor('#14643B'), spaceAfter=12)
    body_style = ParagraphStyle('Body', fontName='DemoDejaVu', fontSize=11, leading=18, spaceAfter=12)
    note_style = ParagraphStyle('Note', parent=body_style, fontSize=9, textColor=colors.HexColor('#555555'))
    doc = SimpleDocTemplate(str(path), title=title, author='БВТ2506', topMargin=22*mm, bottomMargin=22*mm)
    def make_canvas(*args, **kwargs):
        kwargs['invariant'] = 1
        return canvas.Canvas(*args, **kwargs)
    doc.build([Paragraph(escape(title), title_style), Paragraph(escape(DISCLAIMER), note_style),
               Spacer(1, 5*mm), Paragraph(escape(text), body_style)], canvasmaker=make_canvas)


def main():
    source = ROOT / 'data/documents.json'
    records = json.loads(source.read_text(encoding='utf-8'))
    active = {}
    for doc in records:
        if doc['id'] not in active or doc['version'] > active[doc['id']]['version']:
            active[doc['id']] = doc
    manifest = {'schema_version': 1, 'all_materials_synthetic': True,
                'seed_source': 'data/documents.json', 'seed_sha256': sha256(source.read_bytes()).hexdigest(),
                'reference': [], 'uploads': [], 'updates': []}
    for name in ('01-reference', '02-upload', '03-updates'):
        (HERE / name).mkdir(exist_ok=True)
    for doc in sorted(active.values(), key=lambda value: (value['area'], value['id'])):
        relative = f"01-reference/{doc['id']}-v{doc['version']}.md"
        lines = [f"# {doc['title']}", '', DISCLAIMER, '',
                 '> Для чтения. Этот документ уже загружается из исходного корпуса в новую базу. Не загружайте эту копию на основном показе.', '',
                 f"- ID: `{doc['id']}`", f"- Версия: {doc['version']}", f"- Система: `{doc['area']}`",
                 f"- Доступ: {', '.join(doc['roles'])}", f"- Приоритет: {doc['priority']}", f"- Ответственный: {doc['contact']}", '']
        for section in doc['sections']:
            lines += [f"## Раздел `{section['key']}`", '', section['text'], '']
            if section.get('facts'):
                lines += ['Размеченные факты: `' + json.dumps(section['facts'], ensure_ascii=False) + '`.', '']
        (HERE / relative).write_text('\n'.join(lines), encoding='utf-8')
        manifest['reference'].append({'file': relative, 'uploadable': False, 'purpose': 'read_existing_seed',
                                       'id': doc['id'], 'version': doc['version'], 'area': doc['area'], 'roles': doc['roles']})
    for case in CASES:
        path = HERE / case['file']
        suffix = path.suffix
        if suffix == '.json':
            path.write_text(json.dumps(structured(case), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        elif suffix == '.docx':
            from docx import Document
            doc = Document()
            doc.add_heading(case['title'], 0)
            doc.add_paragraph(DISCLAIMER)
            doc.add_paragraph(case['text'])
            doc.save(path)
        elif suffix == '.pdf':
            write_pdf(path, case['title'], case['text'])
        elif suffix == '.txt':
            # Keep the main live-LLM fixture focused on the actual procedure.
            # The title is entered as metadata; synthetic status is in README/UI.
            path.write_text(case['text'] + '\n', encoding='utf-8')
        else:
            path.write_text('# ' + case['title'] + '\n\n' + DISCLAIMER + '\n\n' + case['text'] + '\n', encoding='utf-8')
        key = 'procedure' if suffix == '.json' else 'section-001'
        manifest['uploads'].append({'file': case['file'], 'uploadable': True,
            'purpose': 'new_knowledge', 'format': suffix[1:], 'metadata': metadata(case),
            'question': case['question'], 'marker': case['marker'],
            'expected_before_approval': {'kind': 'missing', 'marker_absent': case['marker']},
            'expected_after_approval': {'kind': 'answer', 'source': f"{case['id']}@1#{key}", 'contains': case['marker']},
            'negative_role_after_approval': 'support' if case['roles'] == ['ib'] else None})
    updated = json.loads((ROOT/'data/update-example.json').read_text(encoding='utf-8'))
    relative = '03-updates/01-access-v3-approve.json'
    (HERE / relative).write_text(json.dumps(updated, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    manifest['updates'].append({'file': relative, 'uploadable': True, 'purpose': 'approve_new_version',
        'question': 'Как получить доступ к реестру?', 'area': 'реестр', 'roles': updated['roles'],
        'expected_before_approval': {'source': 'access@2#request', 'marker_absent': 'КУРС-03'},
        'expected_after_approval': {'source': 'access@3#request', 'contains': 'КУРС-03'}})
    rejected = deepcopy(updated)
    rejected['version'] = 4
    rejected['sections'][0]['text'] = 'Для получения доступа к учебному реестру укажите код КУРС-04.'
    relative = '03-updates/02-access-v4-reject.json'
    (HERE / relative).write_text(json.dumps(rejected, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    manifest['updates'].append({'file': relative, 'uploadable': True, 'purpose': 'reject_proposal',
        'requires': 'approve_access_v3_first', 'question': 'Как получить доступ к реестру?', 'area': 'реестр',
        'expected_after_rejection': {'source': 'access@3#request', 'contains': 'КУРС-03', 'marker_absent': 'КУРС-04'},
        'rejection_reason': 'Не описано согласование руководителем'})
    (HERE/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Generated:', len(manifest['reference']), 'reference files,', len(manifest['uploads']), 'upload examples,', len(manifest['updates']), 'version proposals')


if __name__ == '__main__':
    main()
