"""Diagnostic isolation and expected-outcome checks."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from manual_request import probe
from validate_failures import assess, validate

class Response(io.BytesIO):
    code = 200
    headers = {}

class FailureValidationTests(unittest.TestCase):
    @patch.dict(os.environ, {'CHUTES_API_KEY':'real-secret', 'CHUTES_MODEL':'Qwen/Qwen3.8-27B-TEE'})
    def test_diagnostics_do_not_change_next_normal_request(self):
        original = dict(os.environ)
        for case in ('invalid_auth', 'invalid_model', 'invalid_parameter', 'timeout'):
            with self.subTest(case=case):
                with patch('urllib.request.urlopen', return_value=Response(b'{"choices":[]}')) as send:
                    result = probe('chutes','hello',45,True,diagnostic=case)
                request = send.call_args.args[0]
                payload = json.loads(request.data)
                self.assertEqual(result['diagnostic']['case'],case)
                self.assertNotIn('real-secret',json.dumps(result))
                self.assertEqual(os.environ,original)
                if case == 'invalid_auth':self.assertEqual(request.get_header('Authorization'),'Bearer provider-eval-invalid-key')
                if case == 'invalid_model':
                    self.assertEqual(payload['model'],'provider-eval-nonexistent-model')
                    self.assertIsNone(result['metrics']['input_price_per_1m']['value'])
                if case == 'invalid_parameter':self.assertIsInstance(payload['temperature'],str)
                if case == 'timeout':self.assertEqual(send.call_args.kwargs['timeout'],.001)
        with patch('urllib.request.urlopen',return_value=Response(b'{"choices":[]}')) as send:
            result=probe('chutes','hello',45)
        self.assertNotIn('diagnostic',result)
        self.assertEqual(json.loads(send.call_args.args[0].data)['temperature'],0)
        self.assertEqual(send.call_args.args[0].get_header('Authorization'),'Bearer real-secret')

    @patch.dict(os.environ, {'CHUTES_API_KEY':'test'})
    def test_wrong_failure_is_review(self):
        error=urllib.error.HTTPError('https://example.com',503,'Unavailable',{},io.BytesIO(b'Unavailable'))
        with patch('urllib.request.urlopen',side_effect=error):
            r=probe('chutes','hello',45,diagnostic='invalid_auth')
        self.assertFalse(assess(r,'invalid_auth',True)['passed'])
        self.assertFalse(assess(r,'mixed',False)['passed'])
        self.assertFalse(assess(r,'timeout',True)['passed'])

    def test_summary_marks_expected_failure_as_pass_and_keeps_controls(self):
        def fake_probe(provider,prompt,timeout,streaming,diagnostic):
            failing=diagnostic is not None
            r={'provider':provider,'model':'test','provider_model_id':'test','success':not failing,
               'response':{'status_code':401 if failing else 200,'body':{}},'request':{},
               'error':{'type':'HTTPError','message':'Unauthorized'} if failing else None,'total_latency_seconds':1}
            from measurements import normalize
            return normalize(r)
        with tempfile.TemporaryDirectory() as tmp, patch('validate_failures.probe',side_effect=fake_probe):
            output=Path(tmp)/'run'
            rows=validate(output,['venice','chutes'],['mixed'],[False],45)
            self.assertTrue(all(r['passed'] for r in rows))
            self.assertEqual(json.loads((output/'summary.json').read_text())['total'],2)
            self.assertIn('2 / 2 checks passed',(output/'index.html').read_text())
            self.assertTrue((output/'non-streaming-mixed/report.html').exists())
