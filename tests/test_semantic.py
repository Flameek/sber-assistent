"""Запасной смысловой поиск: проверяем логику с заглушкой вместо модели (PyTorch не нужен)."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kb import semantic
from kb.backend import Local
from kb.rag import Assistant
from kb.store import Store
from kb.topics import names_other_system

PARAPHRASE = 'Что нужно, чтобы меня пустили в реестр инцидентов?'


def closest(ref_prefix, score):
    """Заглушка модели: «самым похожим» объявляет раздел с нужным идентификатором."""
    def best_match(rows, question):
        for row in rows:
            if row['ref'].startswith(ref_prefix):
                return row, score
        return None, 0.0
    return best_match


class SemanticFallbackTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.assistant = Assistant(Store(Path(self.directory.name) / 'test.sqlite'), Local(), search_only=True)

    def tearDown(self):
        self.directory.cleanup()

    def ask(self, role, question, area='реестр', ref='access@2', score=0.9, enabled='1'):
        with patch.dict(os.environ, KB_SEMANTIC=enabled), patch.object(semantic, 'best_match', closest(ref, score)):
            return self.assistant.ask(role, question, area)

    def test_disabled_by_default_keeps_old_behaviour(self):
        self.assertEqual(self.ask('support', PARAPHRASE, enabled='0')['kind'], 'missing')

    def test_paraphrase_is_answered_by_meaning_and_priority_still_applies(self):
        # Заглушка указывает на памятку (приоритет 10), но выбирается операция,
        # и по приоритету побеждает действующая инструкция access@2.
        result = self.ask('support', PARAPHRASE, ref='memo@1')
        self.assertEqual(result['kind'], 'answer')
        self.assertEqual([s['ref'] for s in result['sources']], ['access@2#request'])
        self.assertIn('по смыслу', result['explanation'])

    def test_below_threshold_is_missing(self):
        self.assertEqual(self.ask('support', PARAPHRASE, score=semantic.THRESHOLD - 0.01)['kind'], 'missing')

    def test_other_system_is_never_matched_by_meaning(self):
        self.assertEqual(self.ask('ib', 'Как получить доступ к почте?')['kind'], 'missing')
        self.assertEqual(self.ask('ib', 'Как подключиться к учебному VPN?')['kind'], 'missing')
        self.assertTrue(names_other_system('Как войти в SIEM?', 'vpn'))
        self.assertFalse(names_other_system('Как войти в SIEM?', 'siem'))
        self.assertFalse(names_other_system('Можно ли переслать выгрузку на личную почту?', 'siem'))
        self.assertTrue(names_other_system('Как получить доступ к почте?', 'siem'))

    def test_closed_section_cannot_be_reached_by_meaning(self):
        # Модель видит только разрешённые роли разделы: закрытого среди них просто нет.
        result = self.ask('support', 'Какую метку ставят, если задето несколько систем?', ref='triage@1')
        self.assertEqual(result['kind'], 'missing')
        self.assertNotIn('УЧ-ИБ-7', result['text'])

    def test_conflict_is_still_detected(self):
        result = self.ask('ib', 'Сколько ждать перед передачей дежурной смене?', ref='escal-a@1')
        self.assertEqual(result['kind'], 'conflict')
