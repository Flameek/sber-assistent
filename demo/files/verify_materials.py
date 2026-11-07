"""Validate committed demo fixtures through the real importer/review/search path.

No LLM is called. Every scenario uses a temporary SQLite database; the user's
working database and files are unchanged.
"""
from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kb.backend import Local
from kb.importer import import_document
from kb.rag import Assistant
from kb.store import Store

HERE = Path(__file__).resolve().parent


def main():
    manifest = json.loads((HERE/'manifest.json').read_text(encoding='utf-8'))
    checks = []
    for entry in manifest['uploads']:
        path = HERE/entry['file']
        content = path.read_bytes()
        doc = import_document(path.name, content, entry['metadata'])
        assert doc['id'] == entry['metadata']['id']
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory)/'fixture.sqlite')
            assistant = Assistant(store, Local(), search_only=True)
            role = 'ib'
            area = doc['area']
            before = assistant.ask(role, entry['question'], area)
            assert before['kind'] == 'missing', (path.name, 'before', before)
            n = store.propose(doc, role, author='fixture-student')
            pending = assistant.ask(role, entry['question'], area)
            assert pending['kind'] == 'missing', (path.name, 'pending', pending)
            store.approve(n, 'lead', reviewer='fixture-lead')
            after = assistant.ask(role, entry['question'], area)
            refs = {r['ref'] for r in after['sources']}
            expected = entry['expected_after_approval']
            assert after['kind'] == 'answer', (path.name, 'after', after)
            assert expected['source'] in refs, (path.name, refs)
            assert entry['marker'] in after['text'], (path.name, entry['marker'], after)
            if entry.get('negative_role_after_approval'):
                negative = assistant.ask(entry['negative_role_after_approval'], entry['question'], area)
                assert negative['kind'] == 'missing', (path.name, negative)
                assert entry['marker'] not in str(negative)
                assert assistant.source('support', area, expected['source']) is None
            checks.append({'file': entry['file'], 'before': before['kind'], 'pending': pending['kind'],
                           'after': after['kind'], 'source': expected['source'],
                           'role_restriction_checked': bool(entry.get('negative_role_after_approval'))})
            print('PASS:', path.name, 'missing → pending/missing → approved/answer', flush=True)
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory)/'all-formats.sqlite')
        assistant = Assistant(store, Local(), search_only=True)
        for entry in manifest['uploads']:
            path=HERE/entry['file']
            document=import_document(path.name,path.read_bytes(),entry['metadata'])
            store.approve(store.propose(document,'ib'),'lead')
        for entry in manifest['uploads']:
            result=assistant.ask('ib',entry['question'],'vpn')
            assert result['kind']=='answer', (entry['file'], result)
            assert entry['marker'] in result['text'], (entry['file'], result)
            assert entry['expected_after_approval']['source'] in {s['ref'] for s in result['sources']}
        print('PASS: all five new instructions coexist in one published base',flush=True)
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory)/'versions.sqlite')
        assistant = Assistant(store, Local(), search_only=True)
        before = assistant.ask('ib', 'Как получить доступ к реестру?')
        assert before['sources'][0]['ref'] == 'access@2#request'
        first, second = manifest['updates']
        path = HERE/first['file']
        store.approve(store.propose(import_document(path.name, path.read_bytes()), 'ib'), 'lead')
        after = assistant.ask('ib', first['question'])
        assert after['sources'][0]['ref'] == 'access@3#request'
        assert 'КУРС-03' in after['text']
        assert assistant.source('ib', 'реестр', 'access@2#request') is None
        path = HERE/second['file']
        n = store.propose(import_document(path.name, path.read_bytes()), 'ib')
        store.reject(n, 'lead', second['rejection_reason'])
        rejected = assistant.ask('ib', second['question'])
        assert rejected['sources'][0]['ref'] == 'access@3#request'
        assert 'КУРС-03' in rejected['text'] and 'КУРС-04' not in rejected['text']
        assert store.reviews('lead')[0]['state'] == 'rejected'
        print('PASS: access v2 → approve v3 → reject v4; v3 remains active', flush=True)
    for entry in manifest['reference']:
        assert (HERE/entry['file']).is_file()
    print('RESULT:', len(checks), 'format examples;', len(manifest['reference']), 'reference files; version review passed')


if __name__ == '__main__':
    main()
