"""Offline legacy reading preserves saved meaning and never exposes private record contents."""

import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspect_legacy import format_text, inspect_document, main, read_record

FIXTURES = Path(__file__).parent / 'fixtures' / 'legacy'


class LegacyReaderTests(unittest.TestCase):
    def fixture(self, name):
        return json.loads((FIXTURES / name).read_text())

    def test_older_summary_keeps_zero_distinct_from_missing(self):
        report = read_record(FIXTURES / 'summary.json')
        first, second = report['observations']
        self.assertEqual(report['counts'], dict(saved=2, successful=1, failed=1, unknown_success=0, expected=2))
        self.assertEqual(report['providers'], ['chutes', 'venice'])
        self.assertEqual(first['request_cost'], 0)
        self.assertEqual(first['ttft_seconds'], 0)
        self.assertIsNone(first['finish_reason'])
        self.assertIsNone(second['request_cost'])
        self.assertIsNone(second['output_tokens'])
        self.assertIn('saved estimated cost: 0 USD', format_text(report))
        self.assertIn('saved estimated cost: Unavailable', format_text(report))
        self.assertIn('API success does not guarantee a final answer.', format_text(report))
        self.assertIn('First-content time includes reasoning chunks.', format_text(report))
        self.assertTrue(report['synthetic_fixture'])

    def test_normalized_record_uses_saved_cost_and_original_metric_definitions(self):
        document = self.fixture('normalized-observation.json')
        original = copy.deepcopy(document)
        report = inspect_document(document)
        row = report['observations'][0]
        self.assertEqual(row['request_cost'], 0.123456789)
        self.assertIsNone(row['input_cost'])
        self.assertEqual(row['output_cost'], 0)
        self.assertEqual(row['finish_reason'], 'stop')
        self.assertEqual(row['output_tokens'], 20)
        self.assertEqual(row['reasoning_tokens'], 5)
        self.assertIn('content/reasoning', report['metric_definitions']['output_tokens_per_second']['meaning'])
        self.assertIn('OR reasoning', report['metric_definitions']['ttft_seconds']['meaning'])
        self.assertIn('NOT APS', report['label'])
        self.assertEqual(document, original)

    def test_no_pricing_reads_network_env_loading_or_file_writes(self):
        path = FIXTURES / 'normalized-observation.json'
        original_bytes = path.read_bytes()
        original_mtime = path.stat().st_mtime_ns
        original_read = Path.read_text
        reads = []

        def only_record_read(target, *args, **kwargs):
            self.assertEqual(target, path, 'Reader attempted to load pricing, secrets, or another record')
            reads.append(target)
            return original_read(target, *args, **kwargs)

        with patch.dict('os.environ', {}, clear=True), \
                patch.object(Path, 'read_text', only_record_read), \
                patch.object(Path, 'write_text', side_effect=AssertionError('Unexpected write')), \
                patch.object(Path, 'write_bytes', side_effect=AssertionError('Unexpected write')), \
                patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected network')), \
                patch('socket.socket', side_effect=AssertionError('Unexpected network')):
            report = read_record(path)
        self.assertEqual(reads, [path])
        self.assertEqual(report['observations'][0]['request_cost'], 0.123456789)
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertEqual(path.stat().st_mtime_ns, original_mtime)

    def test_output_excludes_private_fields_in_both_formats(self):
        for name in ['summary.json', 'normalized-observation.json']:
            with self.subTest(name=name):
                report = read_record(FIXTURES / name)
                for output in [json.dumps(report), format_text(report)]:
                    self.assertNotIn('PRIVATE_', output)
                    self.assertNotIn('synthetic-model', output)
                    self.assertIn('NOT APS', output)

    def test_missing_metrics_are_unavailable_even_when_usage_and_pricing_exist(self):
        document = self.fixture('normalized-observation.json')
        document['metrics'] = {}
        row = inspect_document(document)['observations'][0]
        self.assertTrue(row['success'])
        self.assertIsNone(row['input_tokens'])
        self.assertIsNone(row['output_tokens'])
        self.assertIsNone(row['request_cost'])

    def test_missing_success_remains_unknown(self):
        report = inspect_document({'observations': [{'provider': 'chutes'}]})
        self.assertEqual(report['counts']['unknown_success'], 1)
        self.assertEqual(report['counts']['failed'], 0)
        self.assertIn('API success unknown', format_text(report))

    def test_invalid_or_unsupported_shapes_are_rejected(self):
        invalid = [
            [], {}, {'record_paths': []}, {'observations': {}}, {'observations': [None]},
            {'observations': [{}]}, {'provider': 'chutes', 'metrics': []},
            {'provider': 'chutes', 'metrics': {'request_cost': 0.1}},
            {'provider': 'chutes', 'metrics': {'request_cost': {}}},
            {'observations': [], 'saved_observations': 1},
            {'observations': [], 'expected_observations': True},
            {'observations': [{'provider': 'chutes'}], 'expected_observations': 0},
            {'observations': [{'provider': 'chutes', 'success': 'yes'}]},
            {'observations': [{'provider': 'chutes', 'finish_reason': {'message': 'PRIVATE_ERROR'}}]},
            {'observations': [{'provider': 'chutes\nPRIVATE_PROMPT'}]},
        ]
        for document in invalid:
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    inspect_document(document)
        for bad_value in [-1, float('nan'), float('inf'), True, '0', {}, []]:
            with self.subTest(bad_value=bad_value):
                with self.assertRaises(ValueError):
                    inspect_document({'observations': [{'provider': 'chutes', 'request_cost': bad_value}]})

    def test_cli_reports_actionable_errors_without_raw_content_or_traceback(self):
        for contents, message in [('PRIVATE_INVALID_JSON', 'Invalid JSON'), ('{}', 'Unsupported record')]:
            with self.subTest(contents=contents), patch.object(Path, 'read_text', return_value=contents), \
                    patch('sys.stderr', new_callable=io.StringIO) as stderr:
                with self.assertRaises(SystemExit) as raised:
                    main(['private-record.json'])
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(message, stderr.getvalue())
                self.assertNotIn('PRIVATE_', stderr.getvalue())
                self.assertNotIn('Traceback', stderr.getvalue())
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError('PRIVATE_PATH')):
            with self.assertRaisesRegex(ValueError, 'readable UTF-8 legacy JSON'):
                read_record('missing.json')

    def test_cli_json_is_safe_and_parseable(self):
        with patch('sys.stdout', new_callable=io.StringIO) as stdout:
            main([str(FIXTURES / 'normalized-observation.json'), '--json'])
        report = json.loads(stdout.getvalue())
        self.assertEqual(report['record_kind'], 'normalized_observation')
        self.assertEqual(report['counts']['saved'], 1)
        self.assertNotIn('PRIVATE_', stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
