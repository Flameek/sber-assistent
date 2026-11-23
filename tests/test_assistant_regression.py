"""Регрессионные вопросы через Assistant — тот путь, которым работает приложение.

tests/test_retrieval.py проверяет их через Service, а приложение отвечает через Assistant.
Без этого теста расхождение между ними не видно (так и было с «доступом к почте»).
"""
import json
from pathlib import Path
import tempfile
import unittest

from kb.backend import Local
from kb.corpus import ROOT
from kb.rag import Assistant
from kb.store import Store


class AssistantRegressionTests(unittest.TestCase):
    def test_regression_cases_through_assistant(self):
        cases = json.loads((ROOT / 'data/questions.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            assistant = Assistant(Store(Path(directory) / 'test.sqlite'), Local(), search_only=True)
            for case in cases:
                if case['split'] != 'regression' or not case['question']:
                    continue
                with self.subTest(case=case['id'], question=case['question']):
                    self.assertEqual(assistant.ask(case['role'], case['question'], 'реестр')['kind'], case['expected'])
