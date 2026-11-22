"""Иерархия из 7 ролей: старшая роль видит всё, что младшие, и только тимлид — выгрузку базы пользователей."""
from pathlib import Path
import tempfile
import unittest

from kb.backend import Local
from kb.corpus import ROLES, chunks, seed, with_seniors
from kb.rag import Assistant
from kb.store import Store
from kb.users import Users

EXPORT = 'Как выгрузить базу пользователей реестра?'
EXPORT_REF = 'users-export@1#export'


class RoleHierarchyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.assistant = Assistant(Store(Path(self.directory.name) / 'test.sqlite'), Local(), search_only=True)

    def tearDown(self):
        self.directory.cleanup()

    def test_seniors_inherit_juniors_access(self):
        self.assertEqual(with_seniors(['senior']), ['senior', 'lead'])
        self.assertEqual(with_seniors(['support', 'ib']), list(ROLES))

    def test_each_senior_role_sees_more(self):
        rows = chunks(seed())
        seen = [{r['ref'] for r in rows if role in r['roles']} for role in ROLES]
        for junior, senior in zip(seen, seen[1:]):
            self.assertTrue(junior < senior)

    def test_only_lead_can_get_users_export(self):
        for role in list(ROLES)[:-1]:
            with self.subTest(role=role):
                result = self.assistant.ask(role, EXPORT, 'реестр')
                self.assertEqual(result['kind'], 'missing')
                self.assertNotIn('Экспорт', result['text'])
                self.assertIsNone(self.assistant.source(role, 'реестр', EXPORT_REF))
        result = self.assistant.ask('lead', EXPORT, 'реестр')
        self.assertEqual([s['ref'] for s in result['sources']], [EXPORT_REF])

    def test_requesting_and_granting_write_access_are_different(self):
        # Стажёр спрашивает, как ЗАПРОСИТЬ права на запись: инструкции нет (ловушка R03 команды).
        self.assertEqual(self.assistant.ask('support', 'Как запросить права на запись в реестре?', 'реестр')['kind'], 'missing')
        # Аналитик спрашивает, как ВЫДАТЬ права: это его инструкция.
        result = self.assistant.ask('analyst', 'Как выдать стажёру право на запись в реестр?', 'реестр')
        self.assertEqual([s['ref'] for s in result['sources']], ['grant@1#write'])
        self.assertEqual(self.assistant.ask('ib', 'Как выдать стажёру право на запись в реестр?', 'реестр')['kind'], 'missing')

    def test_new_roles_can_log_in(self):
        with tempfile.TemporaryDirectory() as directory:
            users = Users(Path(directory) / 'users.sqlite')
            users.create('anna', 'long-test-password', 'analyst')
            token = users.login('anna', 'long-test-password')
            self.assertEqual(users.session(token)['profile'], 'analyst')
