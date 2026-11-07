"""Opt-in real LLM evaluation, separate from deterministic retrieval metrics."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from kb.backend import Elastic, Local
from kb.llm import ModelError
from kb.rag import Assistant
from kb.store import Store

load_dotenv(Path(__file__).resolve().parents[1]/'.env', override=False)
CASES = [
    ('A1','ib','реестр','Как получить доступ к реестру?','answer',['access@2#request']),
    ('A2','ib','реестр','Как зарегистрировать инцидент и проверить статус заявки?','answer',['create@1#new','status@1#check']),
    ('A3','support','реестр','Как классифицировать инцидент по влиянию?','missing',[]),
    ('A4','ib','реестр','Какой срок эскалации критического инцидента?','conflict',[]),
    ('A5','ib','реестр','Как отозвать доступ к реестру?','missing',[]),
    ('A6','support','vpn','Как подключиться к учебному VPN?','answer',['vpn-connect@1#procedure']),
    ('A7','ib','siem','Как разобрать событие в SIEM?','answer',['siem-alert@1#procedure']),
    ('A8','ib','siem','Как экспортировать журналы SIEM?','answer',['siem-export@1#procedure']),
    ('A9','support','vpn','Что делать при ошибке сертификата VPN?','answer',['vpn-error@1#procedure']),
    ('A10','ib','реестр','Как оформить командировку?','missing',[]),
]

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',default='docs/evaluation-ai.json')
    parser.add_argument('--backend',choices=('local','elastic'),default='local')
    args = parser.parse_args()
    records = []
    with tempfile.TemporaryDirectory() as directory:
        assistant = Assistant(Store(Path(directory)/'evaluation.sqlite'),Elastic() if args.backend=='elastic' else Local())
        for ident,role,area,q,expected,refs in CASES:
            try:
                result = assistant.ask(role,q,area)
                got = [s['ref'] for s in result['sources']]
                ok = result['kind'] == expected and set(got) == set(refs)
                records.append({'id':ident,'question':q,'expected':expected,'expected_sources':refs,'ok':ok,'result':result,
                                'human_review':'not_done'})
                print(ident, result['kind'], got, result['elapsed_ms'],flush=True)
            except ModelError as error:
                records.append({'id':ident,'question':q,'expected':expected,'ok':False,'error':str(error),'human_review':'not_done'})
                print(ident,'ERROR',str(error),flush=True)
    values = [r['result']['elapsed_ms'] for r in records if r.get('result',{}).get('generated')]
    report = {'model':assistant.model.config.model,'provider':assistant.model.config.provider,'backend':args.backend,
              'queries':len(records),'correct_outcomes_and_sources':sum(r['ok'] for r in records),
              'generated_queries':len(values),'median_generated_ms':round(statistics.median(values),1) if values else None,
              'note':'Checks outcomes and source IDs, not semantic completeness. Human review required.', 'rows':records}
    destination = Path(args.output)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not all(r['ok'] for r in records):
        raise SystemExit(1)
