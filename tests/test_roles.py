import unittest

from kb.backend import Local
from kb.corpus import ROLES, chunks, seed, with_seniors
from kb.service import Service

EXPORT = "Как выгрузить базу пользователей реестра?"
EXPORT_REF = "users-export@1#export"


class RoleHierarchyTests(unittest.TestCase):
    def setUp(self):
        self.s = Service(chunks(seed()), Local())

    def test_seniors_inherit_juniors_access(self):
        self.assertEqual(with_seniors(["senior"]), ["senior", "lead"])
        self.assertEqual(with_seniors(["support", "ib"]), list(ROLES))

    def test_each_senior_role_sees_more(self):
        seen = [{r["ref"] for r in self.s.visible(role)} for role in ROLES]
        for junior, senior in zip(seen, seen[1:]):
            self.assertTrue(junior < senior)

    def test_only_lead_can_get_users_export(self):
        for role in list(ROLES)[:-1]:
            with self.subTest(role=role):
                r = self.s.ask(role, EXPORT)
                self.assertEqual(r["kind"], "missing")
                self.assertNotIn(EXPORT_REF, r["ranked"])
                self.assertNotIn("Экспорт", r["text"])
                self.assertIsNone(self.s.source(role, EXPORT_REF))
        r = self.s.ask("lead", EXPORT)
        self.assertEqual(r["kind"], "answer")
        self.assertEqual(r["source"], EXPORT_REF)