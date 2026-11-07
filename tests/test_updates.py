import json, tempfile, unittest
from pathlib import Path
from kb.corpus import ROOT,chunks
from kb.store import Store
from kb.backend import Local
from kb.service import Service

class UpdateTests(unittest.TestCase):
    def test_publication_changes_answers_while_old_links_disappear(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'db')
            doc=json.loads((ROOT/'data/update-example.json').read_text())
            n=s.propose(doc,"ib")
            def service():return Service(chunks(s.published()),Local())
            def ask():return service().ask("ib","Как получить доступ к реестру?")["text"]
            self.assertNotIn("КУРС-03",ask())
            with self.assertRaises(PermissionError):s.approve(n,"ib")
            with self.assertRaises(PermissionError):s.pending("support")
            s.approve(n,"lead")
            self.assertIn("КУРС-03",ask());self.assertIsNone(service().source("ib","access@2#request"))
            with self.assertRaises(ValueError):s.approve(n,"lead")
            again=s.propose(doc,"lead")
            with self.assertRaises(ValueError):s.approve(again,"lead")
