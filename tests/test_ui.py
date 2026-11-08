import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from kb.corpus import ROOT
from tests.test_rag import FakeModel


class AppTests(unittest.TestCase):
    def test_question_source_and_role_switch_clear_history(self):
        fake = FakeModel()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, KB_BACKEND='local', KB_DEMO_MODE='true', KB_DB=str(Path(tmp)/'db')):
            with patch('kb.llm.ModelClient.complete', side_effect=fake.complete):
                app = AppTest.from_file(str(ROOT/'app.py')).run()
                self.assertFalse(app.exception)
                app.sidebar.selectbox[0].select('ib').run()
                app.chat_input[0].set_value('Как классифицировать инцидент по влиянию?').run()
                self.assertFalse(app.exception)
                self.assertTrue(any('УЧ-ИБ-7' in t.value or 'Категория' in t.value for t in app.text))
                next(b for b in app.button if b.label == 'Открыть раздел инструкции').click().run()
                self.assertIn('triage@1#classify', app.query_params['source'])
                app.sidebar.selectbox[0].select('support').run()
                self.assertFalse(app.exception)
                self.assertFalse(any('УЧ-ИБ-7' in t.value for t in app.text))
                self.assertTrue(any('Раздел недоступен' in t.value for t in app.info))

    def test_default_mode_requires_login(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, KB_BACKEND='local', KB_DEMO_MODE='false', KB_DB=str(Path(tmp)/'db')):
            app = AppTest.from_file(str(ROOT/'app.py')).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.title[0].value, 'Вход в базу знаний')
            self.assertEqual(len(app.chat_input), 0)
