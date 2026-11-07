import os, unittest
from kb.backend import Elastic,Local
from kb.corpus import chunks,seed,ROOT
from kb.service import Service
import json

@unittest.skipUnless(os.getenv("KB_TEST_ES")=="1","Запустите Elasticsearch и задайте KB_TEST_ES=1")
class ElasticIntegration(unittest.TestCase):
    def test_elastic_and_reference_agree_and_do_not_leak(self):
        rows=chunks(seed());a=Service(rows,Elastic());b=Service(rows,Local())
        for q in json.loads((ROOT/"data/questions.json").read_text()):
            with self.subTest(case=q["id"]):
                self.assertEqual(a.ask(q['role'],q['question']),b.ask(q['role'],q['question']))
        self.assertIsNone(a.source("support","triage@1#classify"))
        self.assertIsNotNone(a.source("ib","triage@1#classify"))
