import os, unittest
from kb.backend import Elastic,Local
from kb.corpus import chunks,seed,ROOT
from kb.service import Service
import json

@unittest.skipUnless(os.getenv("KB_TEST_ES")=="1","Запустите Elasticsearch и задайте KB_TEST_ES=1")
class ElasticIntegration(unittest.TestCase):
    def test_rag_publication_uses_new_index_and_preserves_access(self):
        from pathlib import Path
        import tempfile
        from kb.store import Store
        from kb.rag import Assistant
        from tests.test_rag import FakeModel
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'test.sqlite')
            model=FakeModel()
            assistant=Assistant(store,Elastic(),model)
            before=assistant.ask('ib','Как получить доступ к реестру?')
            self.assertEqual(before['sources'][0]['ref'],'access@2#request')
            doc=json.loads((ROOT/'data/update-example.json').read_text())
            store.approve(store.propose(doc,'ib'),'lead')
            after=assistant.ask('ib','Как получить доступ к реестру?')
            self.assertEqual(after['sources'][0]['ref'],'access@3#request')
            self.assertIn('КУРС-03',after['text'])
            self.assertIsNone(assistant.source('ib','реестр','access@2#request'))
            self.assertIsNone(assistant.source('support','реестр','triage@1#classify'))

    def test_elastic_and_reference_agree_and_do_not_leak(self):
        rows=chunks(seed());a=Service(rows,Elastic());b=Service(rows,Local())
        for q in json.loads((ROOT/"data/questions.json").read_text()):
            with self.subTest(case=q["id"]):
                self.assertEqual(a.ask(q['role'],q['question']),b.ask(q['role'],q['question']))
        self.assertIsNone(a.source("support","triage@1#classify"))
        self.assertIsNotNone(a.source("ib","triage@1#classify"))
