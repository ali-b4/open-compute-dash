import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from qualify_providers import check

class QualificationTests(unittest.TestCase):
    def test_http_success_does_not_prove_schema_or_tools(self):
        r={'success':True,'response':{'body':{'choices':[{'message':{'content':'wrong'}}]}}}
        self.assertFalse(check('structured_output',r)[0])
        self.assertFalse(check('tool_calling',r)[0])
        r['response']['body']['choices'][0]['message']['content']='{"answer":"ok"}'
        self.assertTrue(check('structured_output',r)[0])
        r['response']['body']['choices'][0]['message']['tool_calls']=[{'function':{'name':'record_number','arguments':'{"value":7}'}}]
        self.assertTrue(check('tool_calling_auto',r)[0])
        r['success']=False
        self.assertFalse(check('tool_calling_auto',r)[0])
