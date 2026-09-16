"""Check audit boundaries without installing optional tokenizer tools."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_tokens import audit_record

class TokenAuditTests(unittest.TestCase):
    def record(self):
        return {'provider':'darkbloom','model':'qwen/qwen3.8-27b','provider_model_id':'fixed',
                'success':True,'request':{'json':{'messages':[{'role':'user','content':'hi'}]}},
                'response':{'body':{'choices':[{'message':{'content':'answer','reasoning':'thought',
                                                         'reasoning_content':'thought'}}],
                                    'usage':{'prompt_tokens':9,'completion_tokens':32}}}}

    def test_reconstruction_deduplicates_reasoning_and_preserves_source(self):
        r=self.record();before=copy.deepcopy(r)
        template=Mock();template.render.return_value='123456789'
        count=Mock(side_effect=len)
        audit=audit_record(r,count,template)
        self.assertEqual(audit['reconstructed_output'],'thought</think>answer<|im_end|>')
        self.assertEqual(audit['visible_reasoning_tokens'],7)
        self.assertEqual(audit['input_difference'],0)
        self.assertFalse(audit['output_matches'])
        self.assertEqual(r,before)

    def test_missing_usage_is_not_false_match(self):
        r=self.record();r['response']['body']['usage']={}
        template=Mock();template.render.return_value='prompt'
        audit=audit_record(r,len,template)
        self.assertIsNone(audit['input_difference'])
        self.assertIsNone(audit['output_matches'])

    def test_unsupported_and_failed_records_are_unavailable(self):
        for change in ('failed','model','reasoning','tools'):
            with self.subTest(change=change):
                r=self.record()
                if change=='failed':r['success']=False
                if change=='model':r['model']='other'
                if change=='reasoning':r['response']['body']['choices'][0]['message']={'content':'answer'}
                if change=='tools':r['request']['json']['tools']=[{}]
                self.assertFalse(audit_record(r,len,Mock())['available'])
