"""Offline checks that the frozen workload reaches all providers unchanged."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error

from scripts import manual_request
from scripts import run_benchmark as benchmark


WORKLOAD = Path(__file__).with_name('basic_chat.json')
PROVIDERS = ['venice', 'chutes', 'darkbloom']
SETTINGS = {
    'temperature': 0, 'top_p': 1, 'max_tokens': 2048, 'stream': True,
    'timeout_seconds': 180, 'pause_between_requests_seconds': 2,
    'repetitions': 1, 'concurrency': 1,
}
KEYS = {f'{provider.upper()}_API_KEY': 'offline-test-key' for provider in PROVIDERS}
MODELS = {f'{provider.upper()}_MODEL': benchmark.PROVIDERS[provider][1]
          for provider in PROVIDERS}
STREAM = (
    b'data: {"choices":[{"delta":{"content":"Test answer"},"index":0}]}\n\n'
    b'data: {"choices":[{"delta":{},"finish_reason":"stop","index":0}],'
    b'"usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}}\n\n'
    b'data: [DONE]\n\n'
)


class Response(io.BytesIO):
    code = 200
    headers = {'Content-Type': 'text/event-stream'}


class FrozenWorkloadTests(unittest.TestCase):
    def test_load_expands_three_cases_and_records_frozen_identity(self):
        workloads = benchmark.load_workloads([WORKLOAD])
        self.assertEqual([w['name'] for w in workloads],
                         ['short_factual', 'medium_explanation', 'longer_generation'])
        digest = hashlib.sha256(WORKLOAD.read_bytes()).hexdigest()
        for workload in workloads:
            self.assertEqual(workload['providers'], PROVIDERS)
            self.assertEqual(workload['settings'], SETTINGS)
            self.assertEqual(workload['provider_model_ids'],
                             {p: benchmark.PROVIDERS[p][1] for p in PROVIDERS})
            self.assertEqual(workload['source_sha256'], digest)
            self.assertEqual(Path(workload['source_path']), WORKLOAD.resolve())
            self.assertEqual(workload['frozen_workload'], {
                'name': 'basic_chat', 'version': '0.1',
                'frozen_at': '2026-09-15', 'source_sha256': digest,
            })

    def test_missing_checksum_and_byte_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'basic_chat.json'
            path.write_bytes(WORKLOAD.read_bytes())
            with self.assertRaises(ValueError):
                benchmark.load_workloads([path])
            path.with_suffix('.sha256').write_bytes(WORKLOAD.with_suffix('.sha256').read_bytes())
            benchmark.load_workloads([path])
            # Even a formatting-only change invalidates the frozen file.
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaises(ValueError):
                benchmark.load_workloads([path])

    def test_rehashed_invalid_schema_controls_and_model_ids_are_rejected(self):
        source = json.loads(WORKLOAD.read_text())
        variants = []
        extra = copy.deepcopy(source)
        extra['unsupported'] = True
        variants.append((extra, 'identity or fields'))
        settings = copy.deepcopy(source)
        settings['settings']['max_tokens'] = 4096
        variants.append((settings, 'settings changed'))
        model = copy.deepcopy(source)
        model['provider_model_ids']['venice'] = 'different-model'
        variants.append((model, 'provider/model selection changed'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'basic_chat.json'
            for variant, reason in variants:
                with self.subTest(variant=variant):
                    path.write_text(json.dumps(variant))
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    path.with_suffix('.sha256').write_text(f'{digest}  {path.name}\n')
                    with self.assertRaisesRegex(ValueError, reason):
                        benchmark.load_workloads([path])

    def test_mixed_workloads_and_execution_overrides_fail_before_requests_or_output(self):
        workloads = benchmark.load_workloads([WORKLOAD])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / 'legacy.json'
            legacy.write_text(json.dumps({'name': 'legacy', 'model': benchmark.MODEL,
                                         'messages': [{'role': 'user', 'content': 'Hi'}]}))
            with patch('urllib.request.urlopen') as send:
                for paths in ([WORKLOAD, legacy], [legacy, WORKLOAD]):
                    with self.subTest(paths=paths), self.assertRaises(ValueError):
                        benchmark.load_workloads(paths)
                overrides = [
                    {'selected': ['venice']},
                    {'selected': list(reversed(PROVIDERS))},
                    {'modes': [False]}, {'modes': [False, True]},
                    {'repetitions': 2}, {'timeout': 90}, {'pause': 0},
                ]
                for override in overrides:
                    options = dict(selected=None, modes=[True], repetitions=1,
                                   timeout=180, pause=2)
                    options.update(override)
                    with self.subTest(override=override), self.assertRaises(ValueError):
                        benchmark.execute(workloads, run_dir=root / 'run',
                                          summary_dir=root / 'summary', **options)
                    self.assertFalse((root / 'run').exists())
                    self.assertFalse((root / 'summary').exists())
                send.assert_not_called()

    def test_cli_rejects_overrides_before_refreshing_prices(self):
        with patch.object(sys, 'argv', ['run_benchmark', '--workloads', str(WORKLOAD),
                                      '--repetitions', '2']), \
                patch.object(benchmark, 'refresh') as refresh, \
                patch.object(benchmark, 'execute') as execute, \
                patch.object(benchmark, 'load_dotenv'), \
                patch.object(sys, 'stderr', io.StringIO()), \
                self.assertRaises(SystemExit) as error:
            benchmark.main()
        self.assertEqual(error.exception.code, 2)
        refresh.assert_not_called()
        execute.assert_not_called()

    @patch.dict(os.environ, {**KEYS, **MODELS})
    def test_nine_serial_http_requests_preserve_controls_and_audit_trail(self):
        workloads = benchmark.load_workloads([WORKLOAD])
        calls = []
        active = 0
        maximum_active = 0
        lock = threading.Lock()

        class TrackedResponse(Response):
            def __enter__(self):
                nonlocal active, maximum_active
                with lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                # A short real wait exposes overlap if a thread pool is used.
                threading.Event().wait(0.01)
                return super().__enter__()

            def __exit__(self, *args):
                nonlocal active
                with lock:
                    active -= 1
                return super().__exit__(*args)

        def send(request, timeout):
            calls.append((request.full_url, json.loads(request.data), timeout))
            return TrackedResponse(STREAM)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('urllib.request.urlopen', side_effect=send), \
                    patch.object(benchmark.time, 'sleep') as pause:
                summary = benchmark.execute(workloads, None, [True], 1, 180,
                                            root / 'run', root / 'summary', 2)
            self.assertEqual(len(calls), 9)
            self.assertEqual(maximum_active, 1)
            self.assertEqual(pause.call_count, 8)
            self.assertTrue(all(call.args == (2,) for call in pause.call_args_list))
            for (url, payload, timeout), (workload, provider) in zip(
                    calls, [(w, p) for w in workloads for p in PROVIDERS]):
                expected = {
                    'model': benchmark.PROVIDERS[provider][1],
                    'messages': workload['messages'], 'temperature': 0,
                    'top_p': 1, 'max_tokens': 2048, 'stream': True,
                    'stream_options': {'include_usage': True},
                }
                if provider == 'venice':
                    expected['venice_parameters'] = {'include_venice_system_prompt': False}
                self.assertEqual(url, benchmark.PROVIDERS[provider][0])
                self.assertEqual(timeout, 180)
                self.assertEqual(payload, expected)
            self.assertTrue(summary['complete'])
            self.assertEqual(summary['successful_observations'], 9)
            manifest = json.loads((root / 'run' / 'manifest.json').read_text())
            self.assertEqual(manifest['settings'], SETTINGS)
            self.assertEqual(manifest['frozen_workload'], workloads[0]['frozen_workload'])
            self.assertEqual(manifest['workloads'], workloads)
            self.assertEqual(len(manifest['record_paths']), 9)
            self.assertEqual((root / 'run' / 'workload.json').read_bytes(), WORKLOAD.read_bytes())
            self.assertEqual((root / 'run' / 'workload.sha256').read_text().split()[0],
                             workloads[0]['source_sha256'])
            for relative in manifest['record_paths']:
                record = json.loads((root / 'run' / relative).read_text())
                self.assertEqual(record['benchmark']['source_sha256'], workloads[0]['source_sha256'])
                self.assertEqual(record['benchmark']['repetition'], 1)
                self.assertIn(record['benchmark']['workload'], [w['name'] for w in workloads])
                self.assertTrue(record['success'])

    @patch.dict(os.environ, {**KEYS, **MODELS})
    def test_one_failure_is_saved_without_retrying_or_stopping_the_workload(self):
        calls = []

        def send(request, timeout):
            calls.append(request)
            if len(calls) == 2:
                raise urllib.error.HTTPError(request.full_url, 503, 'Unavailable', {},
                                             io.BytesIO(b'{"error":"Unavailable"}'))
            return Response(STREAM)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('urllib.request.urlopen', side_effect=send), patch.object(benchmark.time, 'sleep'):
                summary = benchmark.execute(benchmark.load_workloads([WORKLOAD]), None, [True],
                                            1, 180, root / 'run', root / 'summary', 2)
            self.assertEqual(len(calls), 9)
            self.assertTrue(summary['complete'])
            self.assertEqual(summary['saved_observations'], 9)
            self.assertEqual(summary['successful_observations'], 8)
            failed = json.loads((root / 'run' / 'short_factual-r1-streaming' / 'chutes.json').read_text())
            self.assertFalse(failed['success'])
            self.assertEqual(failed['response']['status_code'], 503)

    @patch.dict(os.environ, {**KEYS, **MODELS})
    def test_rebuilt_summary_flags_a_changed_saved_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('urllib.request.urlopen', side_effect=lambda *args, **kwargs: Response(STREAM)), \
                    patch.object(benchmark.time, 'sleep'):
                summary = benchmark.execute(benchmark.load_workloads([WORKLOAD]), None, [True],
                                            1, 180, root / 'run', root / 'summary', 2)
            self.assertTrue(summary['frozen_workload_check']['passed'])
            record_path = root / 'run' / 'short_factual-r1-streaming' / 'venice.json'
            record = json.loads(record_path.read_text())
            record['request']['json']['max_tokens'] = 4096
            record_path.write_text(json.dumps(record))
            with patch('urllib.request.urlopen') as send:
                rebuilt = benchmark.rebuild_summary(root / 'run', root / 'rebuilt')
                send.assert_not_called()
            check = rebuilt['frozen_workload_check']
            self.assertFalse(check['passed'])
            self.assertEqual(check['checked_requests'], 9)
            self.assertEqual(check['mismatches'], ['short_factual/venice'])
            self.assertIn('Frozen v0.1 request check: REVIEW',
                          (root / 'rebuilt' / 'index.html').read_text())

    @patch.dict(os.environ, {**KEYS, **MODELS})
    def test_capped_answers_keep_length_finish_reason_despite_api_success(self):
        capped_stream = STREAM.replace(b'"finish_reason":"stop"', b'"finish_reason":"length"')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('urllib.request.urlopen', side_effect=lambda *args, **kwargs: Response(capped_stream)), \
                    patch.object(benchmark.time, 'sleep'):
                summary = benchmark.execute(benchmark.load_workloads([WORKLOAD]), None, [True],
                                            1, 180, root / 'run', root / 'summary', 2)
            self.assertTrue(summary['complete'])
            self.assertEqual(summary['successful_observations'], 9)
            for observation in summary['observations']:
                self.assertTrue(observation['success'])
                self.assertEqual(observation['finish_reason'], 'length')
            rebuilt = benchmark.rebuild_summary(root / 'run', root / 'rebuilt')
            self.assertEqual(rebuilt['observations'], summary['observations'])
            report = (root / 'rebuilt' / 'index.html').read_text()
            self.assertIn('<th>Finish reason</th>', report)
            self.assertEqual(report.count('<td>length</td>'), 9)
            self.assertIn('Success describes the API request.', report)

    @patch.dict(os.environ, {**KEYS, **MODELS})
    def test_manual_requests_still_omit_the_new_output_cap_by_default(self):
        with patch('urllib.request.urlopen', return_value=Response(b'{}')) as send:
            manual_request.probe('venice', 'Hello', 180)
        payload = json.loads(send.call_args.args[0].data)
        self.assertEqual(payload['temperature'], 0)
        self.assertNotIn('max_tokens', payload)
        self.assertNotIn('top_p', payload)


if __name__ == '__main__':
    unittest.main()
