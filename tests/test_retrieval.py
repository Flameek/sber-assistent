from copy import deepcopy
import unittest

from kb.backend import Local
from kb.corpus import chunks, seed
from kb.evaluate import evaluate
from kb.service import Service
from kb.store import validate


class RetrievalTests(unittest.TestCase):
    def service(self, documents=None):
        return Service(chunks(seed() if documents is None else documents), Local())

    def test_original_holdout_and_regression_cases(self):
        for split, count in [('dev', 6), ('holdout', 9), ('regression', 30)]:
            with self.subTest(split=split):
                report = evaluate(Local(), split)
                self.assertEqual(report['queries'], count)
                self.assertEqual(report['correct'], count, [r for r in report['rows'] if not r['ok']])

    def test_both_sources_are_cited_for_composite_question(self):
        result = self.service().ask('ib', 'Как зарегистрировать инцидент и проверить статус заявки?')
        self.assertEqual([s['ref'] for s in result['sources']], ['create@1#new', 'status@1#check'])
        self.assertIn('наблюдаемый симптом', result['text'])
        self.assertIn('Состояние', result['text'])

    def test_partial_answer_never_leaks_closed_part(self):
        result = self.service().ask('support', 'Как получить доступ и классифицировать инцидент?')
        self.assertEqual(result['kind'], 'partial')
        self.assertNotIn('УЧ-ИБ-7', str(result))
        self.assertNotIn('triage@', str(result))
        self.assertEqual([p['kind'] for p in result['parts']], ['answer', 'missing'])

    def test_priority_explanation_and_resolved_ranking(self):
        result = self.service().ask('ib', 'Как получить доступ через секретаря?')
        self.assertEqual(result['sources'][0]['ref'], 'access@2#request')
        self.assertEqual(result['ranked'][0], 'access@2#request')
        self.assertIn('приоритет 30', result['explanation'])
        self.assertIn('memo@1#request', result['explanation'])

    def test_same_topic_conflicts_even_with_different_legacy_rules(self):
        docs = [deepcopy(d) for d in seed() if d['id'].startswith('escal-')]
        docs[1]['rule'] = 'another-rule'
        self.assertEqual(self.service(docs).ask('ib', 'Какой срок эскалации?')['kind'], 'conflict')

    def test_different_topics_are_not_conflicts_despite_same_legacy_rule(self):
        docs = [deepcopy(d) for d in seed() if d['id'] in ('create', 'status')]
        for doc in docs:
            doc['rule'] = 'shared-rule'
        result = self.service(docs).ask('ib', 'Как зарегистрировать инцидент и проверить статус заявки?')
        self.assertEqual(result['kind'], 'answer')
        self.assertEqual(len(result['sources']), 2)

    def test_unannotated_different_wording_requests_review_without_claiming_conflict(self):
        docs = [deepcopy(d) for d in seed() if d['id'].startswith('escal-')]
        for doc in docs:
            doc['sections'][0].pop('facts')
        result = self.service(docs).ask('ib', 'Какой срок эскалации?')
        self.assertEqual(result['kind'], 'clarify')
        self.assertEqual(result['sources'], [])
        self.assertIn('совместимость не подтверждена', result['text'])

    def test_same_document_sections_form_one_answer(self):
        doc = deepcopy(seed()[1])
        doc['sections'].append({'key': 'approval', 'topic': 'access-read', 'text': 'Дождитесь согласования руководителя.'})
        result = self.service([doc]).ask('ib', 'Как получить доступ к реестру?')
        self.assertEqual(result['kind'], 'answer')
        self.assertEqual(len(result['sources']), 2)
        self.assertIn('Дождитесь согласования', result['text'])

    def test_empty_prompt_does_not_suggest_closed_topics(self):
        result = self.service().ask('support', '')
        self.assertEqual(result['kind'], 'clarify')
        self.assertNotIn('Классификация', result['explanation'])

    def test_unavailable_operation_can_be_published_with_its_own_topic(self):
        doc = deepcopy(seed()[1])
        doc.update(id='revocation', rule='revocation', title='Отзыв доступа')
        doc['sections'] = [{'key': 'revoke', 'topic': 'access-revoke', 'text': 'Чтобы отозвать доступ, направьте заявку руководителю.'}]
        result = self.service([validate(doc)]).ask('ib', 'Как отозвать доступ к реестру?')
        self.assertEqual(result['kind'], 'answer')
        self.assertEqual(result['source'], 'revocation@2#revoke')
