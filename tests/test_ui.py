import os,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from streamlit.testing.v1 import AppTest
from kb.corpus import ROOT

class AppTests(unittest.TestCase):
    def test_question_link_and_profile_switch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,KB_BACKEND="local",KB_DB=str(Path(tmp)/"db")):
            a=AppTest.from_file(str(ROOT/"app.py")).run()
            a.sidebar.selectbox[0].select("ib").run()
            a.text_input[0].set_value("Как классифицировать инцидент по влиянию?")
            a.button[0].click().run();self.assertFalse(a.exception)
            self.assertTrue(any("УЧ-ИБ-7" in t.value for t in a.text))
            next(b for b in a.button if b.label=="Открыть раздел инструкции").click().run()
            self.assertIn("triage@1#classify",a.query_params["source"])
            a.sidebar.selectbox[0].select("support").run()
            self.assertFalse(a.exception);self.assertFalse(any("УЧ-ИБ-7" in t.value for t in a.text))
            self.assertTrue(any("Раздел недоступен" in t.value for t in a.info))
