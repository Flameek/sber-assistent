"""Small real inference check using only a synthetic instruction."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from kb.backend import Local
from kb.llm import ModelError
from kb.rag import Assistant
from kb.store import Store

load_dotenv(Path(__file__).resolve().parents[1]/'.env', override=False)
if __name__ == '__main__':
    try:
        with tempfile.TemporaryDirectory() as directory:
            result = Assistant(Store(Path(directory)/'check.sqlite'), Local()).ask('ib','Как получить доступ к реестру?')
            print(result['text'])
            print('Model:',result['model'],'time:',result['elapsed_ms'],'ms')
            if not result['generated'] or result['kind'] != 'answer':
                raise SystemExit('Проверка не получила ответ модели')
    except ModelError as error:
        raise SystemExit(str(error))
