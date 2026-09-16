"""Check timing boundaries, reasoning accounting, partial streams, and costs."""
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from manual_request import probe
from streaming import read_stream

class Response(io.BytesIO):
    code = 200
    headers = {}

def event(data):
    return ('data: ' + json.dumps(data) + '\n\n').encode()

class MeasurementsTests(unittest.TestCase):
    @patch.dict(os.environ, {'CHUTES_API_KEY':'test'})
    def test_chutes_rate_headers_preserve_reported_values(self):
        response = Response(b'{"choices":[{"message":{"content":"hi"}}]}')
        response.headers = {
            'X-Chutes-RL-User': '60',
            'X-Chutes-Quota-Total': '0',
            'X-Chutes-Quota-Used': '0',
            'X-Chutes-Quota-Remaining': '0',
            'Retry-After': '2',
            'Content-Type': 'application/json',
        }
        with patch('urllib.request.urlopen', return_value=response):
            r = probe('chutes', 'hi', 1)
        limits = r['metadata']['rate_limits']
        self.assertEqual(limits['value'], {
            'x-chutes-rl-user': '60',
            'x-chutes-quota-total': '0',
            'x-chutes-quota-used': '0',
            'x-chutes-quota-remaining': '0',
            'retry-after': '2',
        })
        self.assertEqual(limits['source'], 'provider-reported')
        self.assertIsNone(limits['unit'])
        self.assertIsNone(limits['reason'])

    def test_timing_ignores_role_and_usage_and_deduplicates_reasoning(self):
        wire = event({'choices':[{'delta':{'role':'assistant'}}]})
        wire += event({'choices':[{'delta':{'reasoning':'think','reasoning_content':'think'}}]})
        wire += event({'choices':[{'delta':{'content':'hello'}}]})
        wire += event({'usage':{'completion_tokens':10}}) + b'data: [DONE]\n\n'
        r = {'response':{}}
        with patch('streaming.time.perf_counter', side_effect=[11,12,14,15,16]):
            read_stream(Response(wire),r,10)
        self.assertEqual(r['stream']['first_token_seconds'],2)
        self.assertEqual(r['stream']['last_token_seconds'],4)
        self.assertEqual(r['stream']['reasoning'],'think')
        self.assertEqual(r['response']['body']['usage']['completion_tokens'],10)

    @patch.dict(os.environ, {'CHUTES_API_KEY':'test'})
    def test_cost_includes_reasoning_once_and_cache_discount(self):
        body = {'choices':[{'message':{'content':'hi'}}], 'usage':{'prompt_tokens':100,'completion_tokens':20,
                'completion_tokens_details':{'reasoning_tokens':15},'prompt_tokens_details':{'cached_tokens':50}}}
        with patch('urllib.request.urlopen',return_value=Response(json.dumps(body).encode())):
            r=probe('chutes','hi',1)
        m=r['metrics']
        self.assertEqual(m['output_tokens']['value'],20)
        self.assertAlmostEqual(m['request_cost']['value'],(50*.32+50*.032+20*2.5)/1e6)
        self.assertIsNone(m['ttft_seconds']['value'])
        self.assertIsNone(m['output_tokens_per_second']['value'])

    @patch.dict(os.environ, {'CHUTES_API_KEY':'test'})
    def test_partial_stream_and_api_error_retained(self):
        for tail in (b'',b'data: bad json\n\n',event({'error':{'message':'overloaded'}})):
            with self.subTest(tail=tail):
                wire=event({'choices':[{'delta':{'content':'partial'}}]})+tail
                with patch('urllib.request.urlopen',return_value=Response(wire)):
                    r=probe('chutes','hi',1,True)
                self.assertFalse(r['success'])
                self.assertEqual(r['stream']['content'],'partial')
                self.assertEqual(r['metrics']['http_status']['value'],200)
                self.assertIsNone(r['metrics']['request_cost']['value'])
                self.assertIsNone(r['metrics']['output_tokens_per_second']['value'])

    @patch.dict(os.environ, {'CHUTES_API_KEY':'test'})
    def test_http_200_api_error_is_failure(self):
        with patch('urllib.request.urlopen',return_value=Response(b'{"error":{"message":"bad"}}')):
            self.assertFalse(probe('chutes','hi',1)['success'])

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key_has_complete_schema_and_null_latency(self):
        r=probe('chutes','hi',1)
        self.assertEqual(len(r['metrics']),15)
        self.assertIsNone(r['metrics']['total_latency_seconds']['value'])
        for m in list(r['metrics'].values())+list(r['metadata'].values()):
            if m['value'] is None:self.assertTrue(m['reason'])

if __name__=='__main__': unittest.main()
