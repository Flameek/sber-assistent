from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from unittest.mock import patch
import time

from kb.backend import Local
from kb.llm import ModelClient, ModelConfig, ModelError
from kb.rag import Assistant, context_excerpt, parse_answer, quotes
from kb.store import Store


class FakeModel:
    config = ModelConfig(model='test-model')

    def __init__(self):
        self.requests = []

    def complete(self, messages, schema=None):
        payload = json.loads(messages[-1]['content'])
        self.requests.append(payload)
        source = payload['sources'][0]
        quote = source['quotes'][0]
        return json.dumps({'status': 'answer', 'steps': [{'text': quote, 'ref': source['ref'], 'quote': quote}],
                           'clarification': ''}, ensure_ascii=False)


class RagTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(Path(self.directory.name) / 'test.sqlite')
        self.model = FakeModel()
        self.a = Assistant(self.store, Local(), self.model)

    def test_real_generation_path_sends_only_authorized_area(self):
        result = self.a.ask('support', 'Как получить доступ к реестру?', 'реестр')
        self.assertTrue(result['generated'])
        self.assertEqual(result['sources'][0]['ref'], 'access@2#request')
        prompt = json.dumps(self.model.requests, ensure_ascii=False)
        self.assertNotIn('УЧ-ИБ-7', prompt)
        self.assertNotIn('siem-', prompt)
        self.assertEqual(len(self.model.requests), 1)

    def test_closed_question_and_conflict_do_not_reach_model(self):
        self.assertEqual(self.a.ask('support', 'Как классифицировать инцидент?')['kind'], 'missing')
        self.assertEqual(self.a.ask('ib', 'Какой срок эскалации критического инцидента?')['kind'], 'conflict')
        self.assertEqual(self.model.requests, [])

    def test_composite_answer_has_independent_sources(self):
        result = self.a.ask('ib', 'Как зарегистрировать инцидент и проверить статус заявки?')
        self.assertEqual({s['ref'] for s in result['sources']}, {'create@1#new', 'status@1#check'})
        self.assertEqual(len(self.model.requests), 2)

    def test_general_document_with_new_topic_can_be_answered(self):
        result = self.a.ask('support', 'Как подключиться к учебному VPN?', 'vpn')
        self.assertEqual(result['kind'], 'answer')
        self.assertTrue(result['generated'])
        self.assertIn('vpn-connect', result['sources'][0]['ref'])

    def test_no_silent_substitution_when_model_fails(self):
        self.model.complete = Mock(side_effect=ModelError('model offline'))
        with self.assertRaises(ModelError):
            self.a.ask('ib', 'Как получить доступ к реестру?')

    def test_search_only_does_not_call_a_model(self):
        a = Assistant(self.store, Local(), search_only=True)
        result = a.ask('ib', 'Как получить доступ к реестру?')
        self.assertFalse(result['generated'])
        self.assertEqual(result['provider'], 'retrieval')
        self.assertEqual(result['kind'], 'answer')

    def test_external_calls_need_explicit_opt_in(self):
        with self.assertRaises(ModelError):
            ModelClient(ModelConfig(provider='gigachat'))
        with self.assertRaises(ModelError):
            ModelClient(ModelConfig(base_url='https://example.com/v1'))

    def test_gigachat_native_authorization_and_token_reuse(self):
        with patch.dict('os.environ', {'GIGACHAT_CREDENTIALS': 'dummy-test-credential', 'GIGACHAT_ACCESS_TOKEN': ''}):
            client = ModelClient(ModelConfig(provider='gigachat', model='GigaChat', external_enabled=True))
            reply = {'choices': [{'message': {'content': '{"status":"missing"}'}}]}
            client.request = Mock(side_effect=[{'access_token': 'dummy-test-token', 'expires_at': (time.time()+3600)*1000}, reply, reply])
            client.complete([{'role':'user','content':'test'}])
            client.complete([{'role':'user','content':'test'}])
            self.assertEqual(client.request.call_count, 3)
            self.assertIn('/oauth', client.request.call_args_list[0].args[0])
            self.assertIn('gigachat.devices.sberbank.ru', client.request.call_args_list[1].args[0])

    def test_source_rechecks_role_and_area(self):
        self.assertIsNotNone(self.a.source('ib', 'реестр', 'triage@1#classify'))
        self.assertIsNone(self.a.source('support', 'реестр', 'triage@1#classify'))
        self.assertIsNone(self.a.source('ib', 'vpn', 'triage@1#classify'))

    def test_bad_index_cannot_override_authoritative_document_permissions(self):
        class BadIndex:
            def candidates(self,rows,role,area):
                return rows
        assistant=Assistant(self.store,BadIndex(),self.model)
        self.assertIsNone(assistant.source('support','реестр','triage@1#classify'))
        result=assistant.ask('support','Как получить доступ к реестру?')
        self.assertNotIn('УЧ-ИБ-7',str(result))
        self.assertNotIn('УЧ-ИБ-7',json.dumps(self.model.requests,ensure_ascii=False))

    def test_invalid_citations_and_numeric_facts_are_not_published(self):
        evidence = {'doc@1#s': {'ref': 'doc@1#s', 'text': 'Подайте заявку в течение 15 минут.'}}
        valid = {'status': 'answer', 'steps': [{'text': 'Подайте заявку в течение 15 минут.',
                  'ref': 'doc@1#s', 'quote': 'Подайте заявку в течение 15 минут.'}], 'clarification': ''}
        self.assertEqual(parse_answer(json.dumps(valid), evidence)['kind'], 'answer')
        for key, value in [('ref', 'secret@1#hidden'), ('quote', 'Выдуманная инструкция для сотрудника.'),
                           ('text', 'Подайте заявку в течение 30 минут.')]:
            bad = json.loads(json.dumps(valid))
            bad['steps'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ModelError):
                parse_answer(json.dumps(bad), evidence)

    def test_unknown_model_output_is_not_published(self):
        for raw in ['not json', '[]', '{"status":"answer","steps":[]}']:
            with self.subTest(raw=raw), self.assertRaises(ModelError):
                parse_answer(raw, {})

    def test_approval_condition_and_prohibition_survive_short_model_answer(self):
        text = 'Экспорт разрешает руководитель ИБ. Создайте заявку на экспорт. После согласования сохраните выгрузку. Пересылка в личную почту запрещена.'
        evidence = {'export@1#s': {'ref': 'export@1#s', 'text': text}}
        raw = json.dumps({'status': 'answer', 'steps': [{'text': 'Создайте заявку на экспорт.',
                         'quote': 'Создайте заявку на экспорт.', 'ref': 'export@1#s'}], 'clarification': ''})
        result = parse_answer(raw, evidence)
        self.assertIn('После согласования', result['text'])
        self.assertIn('разрешает руководитель', result['text'])
        self.assertIn('Пересылка в личную почту запрещена', result['text'])

    def test_procedural_answer_keeps_unselected_imperative_step(self):
        evidence = {'guide@1#s': {'ref':'guide@1#s', 'text':'Откройте портал. Укажите цель и интервал времени.'}}
        raw=json.dumps({'status':'answer','steps':[{'text':'Откройте портал.', 'quote':'Откройте портал.', 'ref':'guide@1#s'}], 'clarification':''})
        self.assertNotIn('Укажите цель', parse_answer(raw,evidence)['text'])
        self.assertIn('Укажите цель', parse_answer(raw,evidence,complete_procedure=True)['text'])

    def test_procedure_preserves_order_and_all_fields_from_source(self):
        text='Экспорт разрешает руководитель. Создайте заявку и укажите цель и интервал времени. После согласования сохраните выгрузку.'
        evidence={'doc@1#s':{'ref':'doc@1#s','text':text}}
        raw=json.dumps({'status':'answer','steps':[{'text':'Сохраните выгрузку.', 'quote':'После согласования сохраните выгрузку.', 'ref':'doc@1#s'}], 'clarification':''})
        result=parse_answer(raw,evidence,complete_procedure=True)['text']
        self.assertLess(result.index('разрешает'),result.index('Создайте'))
        self.assertLess(result.index('Создайте'),result.index('После согласования'))
        self.assertIn('цель и интервал времени',result)

    def test_long_chunk_context_retains_relevant_sentence_near_end(self):
        text=('Общая информация для участников учебного проекта. '*100)+'Код доступа к тестовой системе — АЛЬФА-77.'
        row={'ref':'long@1#s','title':'Учебная инструкция','text':text}
        excerpt=context_excerpt(row,'Какой код доступа к системе?',300)
        self.assertLessEqual(len(excerpt['text']),300)
        self.assertIn('АЛЬФА-77',excerpt['text'])

    def test_polite_procedural_question_preserves_all_required_steps(self):
        result=self.a.ask('ib','Подскажите, как получить доступ к реестру?')
        self.assertIn('Отправьте заявку руководителю',result['text'])
