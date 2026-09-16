"""io.net uses the unchanged experiment contract and four-provider reports."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import manual_request
import provider_config
import render_report

class Response(io.BytesIO):
    code = 200
    headers = {}

class IonetTests(unittest.TestCase):
    @patch.dict(os.environ, {'IONET_API_KEY':'test-secret','IONET_MODEL':'Qwen/Qwen3.8-27B'})
    def test_both_modes_keep_experiment_and_normalize_metrics(self):
        usage={'prompt_tokens':100,'completion_tokens':20,'completion_tokens_details':{'reasoning_tokens':15},'prompt_tokens_details':{'cached_tokens':50}}
        for streaming in (False,True):
            with self.subTest(streaming=streaming):
                body={'choices':[{'message':{'content':'hello'}}],'usage':usage}
                wire=json.dumps(body).encode()
                if streaming:
                    events=[{'choices':[{'delta':{'reasoning_content':'think'}}]}, {'choices':[{'delta':{'content':'hello'}}]}, {'choices':[],'usage':usage}]
                    wire=''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode()+b'data: [DONE]\n\n'
                with patch('urllib.request.urlopen',return_value=Response(wire)) as send:
                    r=manual_request.probe('ionet','Reply with exactly: hello',45,streaming)
                request=send.call_args.args[0]
                expected={'model':'Qwen/Qwen3.8-27B','messages':[{'role':'user','content':'Reply with exactly: hello'}],'temperature':0,'stream':streaming}
                if streaming:expected['stream_options']={'include_usage':True}
                self.assertEqual(json.loads(request.data),expected)
                self.assertEqual(request.full_url,'https://api.intelligence.io.solutions/api/v1/chat/completions')
                self.assertTrue(r['success'])
                self.assertNotIn('test-secret',json.dumps(r))
                self.assertEqual(r['metrics']['output_tokens']['value'],20)
                self.assertAlmostEqual(r['metrics']['request_cost']['value'],(50*.308+50*.154+20*2.73)/1e6)
                with tempfile.TemporaryDirectory() as d:
                    p=Path(d);(p/'ionet.json').write_text(json.dumps(r))
                    html=render_report.render_report(p).read_text()
                    self.assertEqual(html.count('<section>'),4)
                    self.assertIn('<h1>io.net</h1>',html)
                    self.assertIn('repeat(4,minmax(0,1fr))',html)
                    self.assertIn('<summary>Metrics</summary>',html)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key_records_failure(self):
        r=manual_request.probe('ionet','hello',1)
        self.assertFalse(r['success'])
        self.assertIn('IONET_API_KEY',r['error']['message'])
        self.assertEqual(set(manual_request.PROVIDERS),{'venice','chutes','darkbloom','ionet'})
        self.assertIs(manual_request.PROVIDERS,render_report.PROVIDERS)
