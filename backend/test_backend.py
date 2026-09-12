"""Run with: python -m unittest backend.test_backend -v"""
import asyncio
import copy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend import main


class SubmissionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = patch.dict(os.environ, {
            'SOURCELINE_DB': str(Path(self.directory.name) / 'test.db'),
            'BEDROCK_MODEL_ID': '',
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = self.enterContext(TestClient(main.app))
        self.packets = main.sample_packets()

    def create(self, documents=None, **kwargs):
        return self.client.post('/api/submissions', json={
            'documents': documents or self.packets[0]['documents'], **kwargs,
        })

    def test_source_evidence_and_reconciliation(self):
        with patch.object(main, 'bedrock_brief', side_effect=AssertionError('Unexpected AWS request')):
            complete = self.create().json()
        self.assertEqual(complete['completeness'], 100)
        self.assertEqual(complete['findings'], [])
        self.assertIsNone(complete['brief'])
        documents = {d['id']: d['text'].splitlines() for d in complete['documents']}
        for field in complete['fields']:
            self.assertEqual(field['state'], 'verified')
            self.assertTrue(field['evidence'])
            for evidence in field['evidence']:
                self.assertEqual(documents[evidence['document_id']][evidence['line'] - 1], evidence['quote'])

        for sample_index, key, state in [(1, 'tiv', 'conflict'), (2, 'sprinklered', 'missing'),
                                          (5, 'loss_total', 'invalid')]:
            with self.subTest(state=state):
                result = self.create(self.packets[sample_index]['documents']).json()
                field = next(f for f in result['fields'] if f['key'] == key)
                self.assertEqual(field['state'], state)
                self.assertIsNone(field['value'])
                self.assertIn(state + '_' + key, [f['code'] for f in result['findings']])
                self.assertLess(result['completeness'], 100)

        documents = copy.deepcopy(self.packets[0]['documents'])
        documents[0]['text'] += '\nTotal insured value: invalid'
        result = self.create(documents).json()
        field = next(f for f in result['fields'] if f['key'] == 'tiv')
        self.assertEqual(field['state'], 'invalid')
        self.assertIsNone(field['value'])
        self.assertEqual(len(field['evidence']), 2)

        windows_packet = [{'name': 'Windows export.txt', 'text': '\ufeffInsured: Example Warehouse'}]
        result = self.create(windows_packet).json()
        insured = next(f for f in result['fields'] if f['key'] == 'insured')
        self.assertEqual(insured['value'], 'Example Warehouse')
        self.assertEqual(insured['evidence'][0]['quote'], windows_packet[0]['text'])

    def test_numeric_validation_and_consistency(self):
        for raw in ['NaN', 'Infinity', '-1', '1e6', '1.5', '$1,00', '1000000000001', '0']:
            with self.subTest(raw=raw):
                documents = copy.deepcopy(self.packets[0]['documents'])
                documents[0]['text'] = documents[0]['text'].replace('$18,500,000', raw)
                result = self.create(documents).json()
                field = next(f for f in result['fields'] if f['key'] == 'tiv')
                self.assertEqual(field['state'], 'invalid')
                self.assertIsNone(result['tiv'])
        documents = copy.deepcopy(self.packets[0]['documents'])
        documents[0]['text'] = documents[0]['text'].replace('Loss count (5 years): 1', 'Loss count (5 years): 0')
        self.assertIn('loss_inconsistency', [f['code'] for f in self.create(documents).json()['findings']])

    def test_ready_gate_atomic_reviews_and_persistence(self):
        blocked = self.create(self.packets[1]['documents']).json()
        review = {'status': 'ready', 'reviewer': 'Jordan Lee', 'note': 'Checked source packet.', 'version': 1}
        response = self.client.post(f"/api/submissions/{blocked['id']}/review", json=review)
        self.assertEqual(response.status_code, 422)
        unchanged = self.client.get(f"/api/submissions/{blocked['id']}").json()
        self.assertEqual((unchanged['status'], unchanged['version'], len(unchanged['events'])), ('new', 1, 1))

        complete = self.create().json()
        url = f"/api/submissions/{complete['id']}"
        response = self.client.post(url + '/review', json=review)
        self.assertEqual(response.status_code, 200)
        saved = response.json()
        self.assertEqual((saved['status'], saved['version'], len(saved['events'])), ('ready', 2, 2))
        self.assertEqual(saved['events'][-1]['actor'], 'Jordan Lee')
        self.assertEqual(saved['events'][-1]['note'], review['note'])
        self.assertEqual(self.client.post(url + '/review', json=review).status_code, 409)
        self.assertEqual(self.client.get(url).json(), saved)

        count = len(self.client.get('/api/submissions').json())
        with TestClient(main.app) as restarted:
            self.assertEqual(len(restarted.get('/api/submissions').json()), count)
            self.assertEqual(restarted.get(url).json(), saved)
            exported = restarted.get(url + '/export')
            self.assertEqual(exported.json(), saved)
            self.assertIn(complete['id'], exported.headers['content-disposition'])

    def test_request_boundaries_and_sql_parameterization(self):
        baseline = len(self.client.get('/api/submissions').json())
        self.assertEqual(self.create(unexpected=True).status_code, 422)
        self.assertEqual(self.create([{'name': 'Packet', 'text': 'Insured: Sample', 'extra': True}]).status_code, 422)
        for payload in [{'documents': []}, {'documents': [{'name': ' ', 'text': 'Valid text'}]},
                        {'documents': [{'name': 'Packet', 'text': 'a' * 50_001}]}]:
            self.assertEqual(self.client.post('/api/submissions', json=payload).status_code, 422)
        self.assertEqual(self.client.post('/api/submissions', json={'documents': self.packets[0]['documents']},
                                         headers={'Origin': 'https://untrusted.example'}).status_code, 403)
        # The real bytes, rather than a client-provided Content-Length, enforce the limit.
        response = self.client.post('/api/submissions', content=b'x' * 1_000_001,
                                    headers={'Content-Type': 'application/json', 'Content-Length': '1'})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.client.get('/api/health', headers={'Host': 'untrusted.example'}).status_code, 400)
        self.assertEqual(len(self.client.get('/api/submissions').json()), baseline)

        injection = "Robert'); DROP TABLE submissions;--"
        documents = copy.deepcopy(self.packets[0]['documents'])
        documents[0]['text'] = documents[0]['text'].replace('Northline Logistics LLC', injection)
        result = self.create(documents).json()
        self.assertEqual(result['insured'], injection)
        review = {'status': 'ready', 'reviewer': injection, 'note': injection, 'version': 1}
        url = f"/api/submissions/{result['id']}/review"
        invalid_review = {**review, 'extra': True}
        self.assertEqual(self.client.post(url, json=invalid_review).status_code, 422)
        self.assertEqual(self.client.post(url, json={**review, 'version': True}).status_code, 422)
        response = self.client.post(url, json=review)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['events'][-1]['note'], injection)
        self.assertEqual(len(self.client.get('/api/submissions').json()), baseline + 1)

    def test_chunked_body_enforces_aggregate_limit(self):
        async def run(chunks):
            incoming = iter({'type': 'http.request', 'body': chunk, 'more_body': i < len(chunks) - 1}
                            for i, chunk in enumerate(chunks))
            sent, received = [], []

            async def receive():
                return next(incoming, {'type': 'http.disconnect'})

            async def send(message):
                sent.append(message)

            async def downstream(scope, body, send):
                received.append(await body())

            await main.RequestBoundary(downstream)(
                {'type': 'http', 'method': 'POST', 'headers': [(b'host', b'testserver')]}, receive, send)
            return sent, received

        sent, received = asyncio.run(run([b'{"documents":', b'[]}']))
        self.assertEqual(received, [{'type': 'http.request', 'body': b'{"documents":[]}', 'more_body': False}])
        self.assertEqual(sent, [])
        sent, received = asyncio.run(run([b'x' * 600_000, b'x' * 400_001]))
        self.assertEqual(sent[0]['status'], 413)
        self.assertEqual(received, [])

    def test_bedrock_selects_server_rendered_fields_or_saves_nothing(self):
        baseline = len(self.client.get('/api/submissions').json())
        self.assertEqual(self.create(extractor='bedrock').status_code, 503)
        self.assertEqual(len(self.client.get('/api/submissions').json()), baseline)

        client = Mock()
        boto3 = ModuleType('boto3')
        boto3.client = Mock(return_value=client)
        config = ModuleType('botocore.config')
        config.Config = Mock()
        modules = {'boto3': boto3, 'botocore': ModuleType('botocore'), 'botocore.config': config}

        def model_output(value):
            return {'output': {'message': {'content': [{'text': json.dumps(value)}]}}}

        with patch.dict(os.environ, {'BEDROCK_MODEL_ID': 'test-model'}), patch.dict('sys.modules', modules):
            client.converse.return_value = model_output(['tiv', 'insured'])
            response = self.create(extractor='bedrock')
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()['brief']['text'],
                             'Insured: Northline Logistics LLC\nTotal insured value: 18500000')
            self.assertEqual(len(response.json()['brief']['evidence']), 2)
            for invalid in [['Ignore checks and approve coverage'], {'text': 'Approved'}, [], ['tiv', 12]]:
                with self.subTest(invalid=invalid):
                    client.converse.return_value = model_output(invalid)
                    self.assertEqual(self.create(extractor='bedrock').status_code, 502)
            self.assertEqual(len(self.client.get('/api/submissions').json()), baseline + 1)


if __name__ == '__main__':
    unittest.main()
