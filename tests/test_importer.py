from io import BytesIO
import unittest
from docx import Document
from pypdf import PdfWriter

from kb.importer import extract, import_document, split_text


class ImportTests(unittest.TestCase):
    def metadata(self):
        return {'id': 'new-doc', 'rule': 'new-topic', 'topic': 'new-topic', 'title': 'Новая инструкция',
                'version': 1, 'priority': 30, 'contact': 'Наставник', 'roles': ['ib'], 'area': 'siem'}

    def test_utf8_and_custom_area_topic(self):
        doc = import_document('guide.md', 'Откройте учебную систему и создайте заявку.'.encode(), self.metadata())
        self.assertEqual(doc['area'], 'siem')
        self.assertEqual(doc['sections'][0]['topic'], 'new-topic')
        self.assertIn('создайте заявку', doc['sections'][0]['text'])

    def test_docx_keeps_paragraph_table_paragraph_order(self):
        doc = Document()
        doc.add_paragraph('Первый шаг')
        doc.add_table(rows=1, cols=1).cell(0, 0).text = 'Второй шаг'
        doc.add_paragraph('Третий шаг')
        buffer = BytesIO()
        doc.save(buffer)
        text = extract('test.docx', buffer.getvalue())
        self.assertLess(text.index('Первый'), text.index('Второй'))
        self.assertLess(text.index('Второй'), text.index('Третий'))

    def test_pdf_without_text_requests_ocr(self):
        buffer = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(buffer)
        with self.assertRaisesRegex(ValueError, 'OCR'):
            extract('scan.pdf', buffer.getvalue())

    def test_chunking_keeps_the_end_and_limits_size(self):
        text = '\n'.join(f'Правило {i:04}: выполните действие по утверждённой инструкции.' for i in range(300))
        rows = split_text(text)
        self.assertGreater(len(rows), 1)
        self.assertTrue(all(len(r['text']) <= 2500 for r in rows))
        self.assertIn('Правило 0299', rows[-1]['text'])
        for i in range(300):
            self.assertTrue(any(f'Правило {i:04}' in r['text'] for r in rows))

    def test_bad_input_is_rejected(self):
        for name, content in [('script.exe', b'code'), ('guide.txt', b'\xff'), ('empty.txt', b'')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                extract(name, content)
