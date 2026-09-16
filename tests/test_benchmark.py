"""Workload validation, concurrency, failure retention, and offline rebuilding."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_benchmark as benchmark
from scripts.measurements import normalize

class BenchmarkTests(unittest.TestCase):
    def test_rejects_invalid_workloads_before_requests(self):
        base={'name':'test','model':benchmark.MODEL,'messages':[{'role':'user','content':'hi'}]}
        variants=[{**base,'name':'../escape'},{**base,'model':'other'}, {**base,'temperature':1},
                  {**base,'messages':[]},{**base,'providers':['other']},{**base,'messages':[{'role':'tool','content':'x'}]}]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'workload.json'
            for value in variants:
                p.write_text(json.dumps(value))
                with self.subTest(value=value),self.assertRaises(ValueError):benchmark.load_workloads([p])
            p.write_text(json.dumps(base))
            with self.assertRaises(ValueError):benchmark.load_workloads([p,p])

    def test_concurrency_failure_retention_and_rebuild(self):
        barrier=threading.Barrier(2);seen=[]
        class Adapter:
            def __init__(self,provider):self.provider=provider
            def chat(self,messages,streaming,timeout):
                barrier.wait(timeout=3);seen.append((self.provider,messages,streaming))
                if self.provider=='chutes':raise RuntimeError('adapter crashed')
                return normalize({'provider':self.provider,'model':benchmark.MODEL,'provider_model_id':benchmark.PROVIDERS[self.provider][1],
                    'timestamp':'test','success':True,'error':None,'response':{'status_code':200,'headers':{},'body':{'usage':{'prompt_tokens':5,'completion_tokens':2}}},
                    'request':{'json':{'messages':messages,'stream':streaming}},'total_latency_seconds':1})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w={'name':'test','model':benchmark.MODEL,'providers':['venice','chutes'],
                             'messages':[{'role':'user','content':'hi'}],'source_sha256':'x'}
            with patch.dict(benchmark.ADAPTERS,{'venice':lambda:Adapter('venice'),'chutes':lambda:Adapter('chutes')}):
                s=benchmark.execute([w],None,[False,True],1,1,root/'raw',root/'summary',0)
            self.assertEqual(len(seen),4)
            self.assertEqual(s['saved_observations'],4)
            self.assertEqual(s['successful_observations'],2)
            self.assertTrue(s['complete'])
            self.assertEqual(s,benchmark.rebuild_summary(root/'raw',root/'rebuild'))
            paths=list((root/'raw').glob('*/chutes.json'))
            self.assertEqual(len(paths),2)
            self.assertTrue(all(json.loads(p.read_text())['error']['type']=='AdapterError' for p in paths))
            r=json.loads(paths[0].read_text());r['validation']={'exclude_from_benchmark':True};paths[0].write_text(json.dumps(r))
            with self.assertRaises(ValueError):benchmark.rebuild_summary(root/'raw',root/'rebuild')

    def test_actual_adapter_forwards_message_history(self):
        from providers.ionet import IonetProvider
        messages=[{'role':'system','content':'Be brief'},{'role':'user','content':'Hi'}]
        with patch('scripts.manual_request.probe',return_value={'success':True}) as probe:
            self.assertTrue(IonetProvider().chat(messages,streaming=True,timeout=2)['success'])
        self.assertEqual(probe.call_args.kwargs['messages'],messages)
        self.assertEqual(probe.call_args.args,('ionet','',2,True))
