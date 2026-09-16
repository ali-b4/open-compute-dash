import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_pricing as pricing

class PricingTests(unittest.TestCase):
    def test_units_and_missing_cache_rate(self):
        r={'id':'model','input_token_price':.000000308,'output_token_price':.00000273,
           'cache_read_token_price':.000000154,'context_window':65536,'precision':'fp8'}
        p=pricing.parse('ionet',r,{},'today')
        self.assertAlmostEqual(p['input_per_1m_tokens'],.308)
        self.assertAlmostEqual(p['output_per_1m_tokens'],2.73)
        r.pop('cache_read_token_price')
        self.assertNotIn('cache_input_per_1m_tokens',pricing.parse('ionet',r,p,'tomorrow'))
        r['input_token_price']=float('nan')
        with self.assertRaises(ValueError):pricing.parse('ionet',r,{},'today')

    def test_failed_fetch_does_not_change_active_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config').mkdir();p=root/'config/pricing.json';p.write_text('{"model":"fixed"}')
            before=p.read_bytes()
            with patch('refresh_pricing.fetch',side_effect=RuntimeError('offline')):
                with self.assertRaises(RuntimeError):pricing.refresh(['venice'],root)
            self.assertEqual(p.read_bytes(),before)

    def test_exact_model_and_archive(self):
        with self.assertRaises(ValueError):pricing.select_model({'data':[{'id':'wrong'}]},'wanted')
        record={'id':pricing.PROVIDERS['venice'][1],'context_length':262144,
                'model_spec':{'pricing':{'input':{'usd':.45},'output':{'usd':3.2}},'capabilities':{'quantization':'fp8'}}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config').mkdir();p=root/'config/pricing.json';p.write_text('{"model":"fixed"}')
            with patch('refresh_pricing.fetch',return_value={'data':[record]}):archive=pricing.refresh(['venice'],root)
            self.assertTrue((archive/'previous-pricing.json').exists())
            self.assertEqual(json.loads(p.read_text())['venice']['input_per_1m_tokens'],.45)
            self.assertEqual(json.loads((archive/'venice.json').read_text())['record'],record)
