from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from kb.corpus import ROOT, chunks, seed
from kb.store import Store, validate


class ReviewTests(unittest.TestCase):
    def test_rejection_preserves_published_documents_and_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.sqlite')
            before = store.published()
            doc = json.loads((ROOT / 'data/update-example.json').read_text())
            n = store.propose(doc, 'support')
            with self.assertRaises(PermissionError):
                store.reject(n, 'ib', 'Нет согласования')
            with self.assertRaises(ValueError):
                store.reject(n, 'lead', '   ')
            store.reject(n, 'lead', 'Нужно уточнить порядок согласования')
            self.assertEqual(store.published(), before)
            self.assertEqual(store.pending('lead'), [])
            record = Store(store.path).reviews('lead')[0]
            self.assertEqual(record['state'], 'rejected')
            self.assertEqual(record['author'], 'support')
            self.assertEqual(record['reviewer'], 'lead')
            self.assertTrue(record['created_at'] and record['resolved_at'])
            self.assertIn('уточнить', record['comment'])
            with self.assertRaises(ValueError):
                store.approve(n, 'lead')

    def test_previous_database_is_migrated_without_losing_pending_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'old.sqlite'
            doc = seed()[1]
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE docs (id TEXT, v INTEGER, body TEXT NOT NULL, PRIMARY KEY(id,v))')
                db.execute('CREATE TABLE proposals (n INTEGER PRIMARY KEY, body TEXT NOT NULL, state TEXT NOT NULL)')
                db.execute('INSERT INTO docs VALUES (?,?,?)', (doc['id'], doc['version'], json.dumps(doc)))
                new = deepcopy(doc)
                new['version'] += 1
                db.execute("INSERT INTO proposals VALUES (1,?,'pending')", (json.dumps(new),))
            store = Store(path)
            self.assertEqual(len(store.published()), 1)
            self.assertEqual(store.pending('lead')[0][0], 1)
            store.approve(1, 'lead')
            self.assertEqual(store.reviews('lead')[0]['reviewer'], 'lead')
            self.assertEqual(len(store.published()), 2)

    def test_section_cannot_override_document_permissions(self):
        doc = deepcopy(next(d for d in seed() if d['id'] == 'triage'))
        doc['sections'][0]['roles'] = ['support']
        with self.assertRaises(ValueError):
            validate(doc)
        # Even legacy data never overrides document-level access during chunking.
        self.assertEqual(chunks([doc])[0]['roles'], ['ib'])

    def test_approval_records_author_and_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'test.sqlite')
            doc = json.loads((ROOT / 'data/update-example.json').read_text())
            n = store.propose(doc, 'ib')
            store.approve(n, 'lead')
            record = store.reviews('lead')[0]
            self.assertEqual((record['author'], record['reviewer'], record['state']), ('ib', 'lead', 'approved'))
            with self.assertRaises(PermissionError):
                store.reviews('support')
