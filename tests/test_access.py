import unittest
from kb.service import Service
from kb.backend import Local
from kb.corpus import chunks, seed

class AccessTests(unittest.TestCase):
    def setUp(self):
        self.s=Service(chunks(seed()),Local())
    def test_link_and_retrieval_use_same_permissions(self):
        ref="triage@1#classify"; secret="УЧ-ИБ-7"
        self.assertIn(secret,self.s.source("ib",ref)["text"])
        for role in ("support","badrole"):
            self.assertIsNone(self.s.source(role,ref))
            ans=self.s.ask(role,"Как классифицировать инцидент по влиянию?")
            self.assertNotIn(ref,ans["ranked"])
            self.assertNotIn(secret,ans["text"])
            self.assertEqual(ans["kind"],"missing")
    def test_archive_not_available_by_old_link(self):
        self.assertIsNone(self.s.source("ib","access@1#request"))
        self.assertEqual(self.s.ask("ib","Как получить доступ к реестру?")["source"],"access@2#request")
    def test_equal_priority_conflict_does_not_guess(self):
        r=self.s.ask("ib","Какой срок эскалации критического инцидента?")
        self.assertEqual(r["kind"],"conflict")
        self.assertIsNone(r["source"])
    def test_unrelated_question(self):
        self.assertEqual(self.s.ask("ib","Как оформить командировку?")["kind"],"missing")
