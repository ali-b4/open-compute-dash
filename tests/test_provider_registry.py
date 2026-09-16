"""Registry selection is extensible, explicitly unverified, and entirely offline."""

import builtins
import copy
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import provider_config as legacy
from scripts import provider_registry as registry


FIXTURE = Path(__file__).parent / 'fixtures/registry/five-providers.json'


class ProviderRegistryTests(unittest.TestCase):
    def setUp(self):
        self.document = registry.load_registry()

    def test_launch_selection_preserves_historical_endpoints_without_verifying_them(self):
        plan = registry.build_provider_plan(self.document)
        endpoints = {p['provider_id']: (p['endpoint_url'], p['model_id']) for p in plan['providers']}
        self.assertEqual(endpoints, legacy.PROVIDERS)
        self.assertEqual(plan['canonical_model_family'], legacy.MODEL)
        self.assertEqual(plan['provider_count'], 4)
        self.assertFalse(plan['synthetic'])
        self.assertEqual(plan['network_requests'], 0)
        self.assertFalse(plan['live_run_authorized'])
        for provider in plan['providers']:
            self.assertEqual(provider['display_name'], legacy.PROVIDER_LABELS[provider['provider_id']])
            self.assertEqual(provider['status'], 'verification_pending')
            self.assertTrue(all(item['status'] == 'unknown' for item in provider['evidence'].values()))
            self.assertEqual(provider['pricing']['status'], 'historical_unverified')
            self.assertEqual(provider['pricing']['config_file'], 'config/pricing.json')
            self.assertEqual(provider['pricing']['config_key'], provider['provider_id'])
        self.assertEqual(plan['required_secret_variables'],
                         ['VENICE_API_KEY', 'CHUTES_API_KEY', 'DARKBLOOM_API_KEY', 'IONET_API_KEY'])

    def test_fictional_provider_is_selected_but_deferred_pearl_needs_no_key(self):
        original = copy.deepcopy(legacy.PROVIDERS)
        plan = registry.build_provider_plan(registry.load_registry(FIXTURE))
        self.assertTrue(plan['synthetic'])
        self.assertEqual(plan['provider_count'], 5)
        fictional = next(p for p in plan['providers'] if p['provider_id'] == 'example_lab')
        self.assertIn('.invalid/', fictional['endpoint_url'])
        self.assertEqual(fictional['pricing']['status'], 'unknown')
        self.assertIn('EXAMPLE_LAB_TEST_KEY', plan['required_secret_variables'])
        self.assertNotIn('PEARL_API_KEY', plan['required_secret_variables'])
        self.assertEqual(plan['excluded_providers'],
                         [{'provider_id': 'pearl', 'display_name': 'Pearl', 'status': 'access_pending'}])
        self.assertEqual(legacy.PROVIDERS, original)

    def test_explicit_selection_keeps_requested_order_and_rejects_unusable_ids(self):
        document = registry.load_registry(FIXTURE)
        plan = registry.build_provider_plan(document, ['example_lab', 'ionet'])
        self.assertEqual([p['provider_id'] for p in plan['providers']], ['example_lab', 'ionet'])
        self.assertEqual(plan['provider_count'], 2)
        self.assertEqual(plan['required_secret_variables'], ['EXAMPLE_LAB_TEST_KEY', 'IONET_API_KEY'])
        self.assertEqual(registry.build_provider_plan(document, [])['provider_count'], 0)
        for selection in [['pearl'], ['unregistered'], ['venice', 'venice'], 'venice', [True]]:
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                registry.build_provider_plan(document, selection)

    def test_registry_changes_drive_selection_without_named_provider_branches(self):
        document = registry.load_registry(FIXTURE)
        document['providers'] = [p for p in document['providers'] if p['provider_id'] != 'chutes']
        document['providers'][0].update(enabled=False, status='disabled')
        added = copy.deepcopy(next(p for p in document['providers'] if p['provider_id'] == 'example_lab'))
        added.update(provider_id='another_endpoint', display_name='Another synthetic endpoint',
                     endpoint_url='https://another.invalid/v1/chat/completions',
                     secret_env_var='SEPARATE_ACCOUNT_TOKEN', model_id='synthetic/another-model')
        document['providers'].append(added)
        plan = registry.build_provider_plan(document)
        self.assertEqual([p['provider_id'] for p in plan['providers']],
                         ['darkbloom', 'ionet', 'example_lab', 'another_endpoint'])
        self.assertEqual(plan['provider_count'], 4)
        self.assertIn('SEPARATE_ACCOUNT_TOKEN', plan['required_secret_variables'])
        self.assertNotIn('VENICE_API_KEY', plan['required_secret_variables'])
        self.assertNotIn('CHUTES_API_KEY', plan['required_secret_variables'])
        with self.assertRaises(ValueError):
            registry.build_provider_plan(document, ['venice'])
        added['secret_env_var'] = 'EXAMPLE_LAB_TEST_KEY'
        self.assertEqual(registry.build_provider_plan(document)['required_secret_variables'].count(
            'EXAMPLE_LAB_TEST_KEY'), 1)

    def test_plan_is_independent_of_source_registry_and_other_plans(self):
        before = copy.deepcopy(self.document)
        first = registry.build_provider_plan(self.document)
        second = registry.build_provider_plan(self.document)
        first['providers'][0]['evidence']['access']['reason'] = 'Changed only in this plan'
        first['providers'][0]['pricing']['status'] = 'changed'
        first['required_secret_variables'].clear()
        self.assertEqual(self.document, before)
        self.assertEqual(second, registry.build_provider_plan(self.document))

    def test_invalid_schema_endpoint_and_secret_configuration_are_rejected(self):
        cases = [
            (('schema_version',), 'unsupported'), (('synthetic',), 1),
            (('unexpected',), True), (('providers',), {}),
            (('providers', 0, 'enabled'), 'true'), (('providers', 0, 'enabled'), 1),
            (('providers', 0, 'status'), 'access_pending'),
            (('providers', 0, 'adapter_type'), 'unreviewed_adapter'),
            (('providers', 0, 'secret_env_var'), 'Bearer private-value'),
            (('providers', 0, 'secret_env_var'), 'lower_case_key'),
            (('providers', 0, 'api_key'), 'PRIVATE_VALUE'),
            (('providers', 0, 'endpoint_url'), 'http://example.invalid/v1/chat/completions'),
            (('providers', 0, 'endpoint_url'), 'https://user:password@example.invalid/v1'),
            (('providers', 0, 'endpoint_url'), 'https://example.invalid/v1?key=PRIVATE_VALUE'),
            (('providers', 0, 'endpoint_url'), 'https://example.invalid/v1#fragment'),
            (('providers', 0, 'endpoint_url'), 'https://%zz/v1/chat/completions'),
            (('providers', 0, 'endpoint_url'), 'https://api.example.com\\bad/v1/chat/completions'),
            (('providers', 0, 'endpoint_url'), 'https://api..example.com/v1'),
            (('providers', 0, 'endpoint_url'), 'https://-api.example.com/v1'),
            (('providers', 0, 'pricing', 'config_file'), '../private-pricing.json'),
            (('providers', 0, 'pricing', 'status'), 'verified'),
        ]
        for path, value in cases:
            document = copy.deepcopy(self.document)
            target = document
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                registry.validate_registry(document)
        duplicate = copy.deepcopy(self.document)
        duplicate['providers'].append(copy.deepcopy(duplicate['providers'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            registry.validate_registry(duplicate)
        for endpoint in ['https://127.0.0.1:8443/v1', 'https://[::1]:8443/v1']:
            document = copy.deepcopy(self.document)
            document['providers'][0]['endpoint_url'] = endpoint
            with self.subTest(valid_endpoint=endpoint):
                registry.validate_registry(document)

    def test_evidence_requires_consistent_unknowns_types_and_provenance(self):
        known = dict(value=True, status='documented', source='https://example.invalid/docs',
                     checked_at='2026-09-16', reason='Synthetic documentation example only.')
        invalid = [
            {**known, 'status': 'unknown'}, {**known, 'value': None},
            {**known, 'source': None}, {**known, 'checked_at': 'yesterday'},
            {**known, 'value': 1}, {**known, 'value': 'true'}, {**known, 'unexpected': True},
        ]
        for evidence in invalid:
            document = copy.deepcopy(self.document)
            document['providers'][0]['evidence']['access'] = evidence
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                registry.validate_registry(document)
        document = copy.deepcopy(self.document)
        document['providers'][0]['evidence']['access'] = {**known, 'value': False}
        self.assertFalse(registry.build_provider_plan(document)['providers'][0]['evidence']['access']['value'])
        for value in [True, 0, -1, 1.5, float('inf')]:
            document['providers'][0]['evidence']['context_window_tokens'] = {**known, 'value': value}
            with self.subTest(context=value), self.assertRaises(ValueError):
                registry.validate_registry(document)

    def test_json_loader_rejects_ambiguous_keys_and_nonfinite_values(self):
        text = json.dumps(self.document)
        invalid = [
            text.replace('"synthetic": false', '"synthetic": true, "synthetic": false', 1),
            text.replace('"enabled": true', '"enabled": false, "enabled": true', 1),
            text.replace('"value": null', '"value": NaN', 1),
            'not valid JSON',
        ]
        for contents in invalid:
            with self.subTest(contents=contents[:50]), patch.object(Path, 'read_text', return_value=contents):
                with self.assertRaises(ValueError):
                    registry.load_registry('synthetic-invalid.json')

    def test_fresh_import_load_and_plan_read_only_registry_and_never_access_services(self):
        source_path = Path(registry.__file__)
        code = compile(source_path.read_text(), str(source_path), 'exec')
        original_open, original_import = io.open, builtins.__import__
        reads = []
        forbidden = {'providers', 'manual_request', 'refresh_pricing', 'run_benchmark', 'measurements'}

        def checked_import(name, globals=None, locals=None, fromlist=(), level=0):
            self.assertFalse(forbidden.intersection(name.split('.') + list(fromlist or ())),
                             'Offline planning imported an inherited service or adapter')
            return original_import(name, globals, locals, fromlist, level)

        def registry_only_open(path, mode='r', *args, **kwargs):
            self.assertEqual(Path(path), FIXTURE, 'Unexpected secret, pricing, or evidence file access')
            self.assertIn(mode, ('r', 'rt'), 'Offline planning attempted to write')
            reads.append(Path(path))
            return original_open(path, mode, *args, **kwargs)

        def forbidden_action(*args, **kwargs):
            raise AssertionError('Offline planning attempted environment, network, or filesystem mutation')

        class NoEnvironment:
            get = __getitem__ = __contains__ = __iter__ = forbidden_action

        namespace = {'__name__': 'scripts.registry_isolation', '__file__': str(source_path),
                     '__package__': 'scripts'}
        with patch('urllib.request.urlopen', side_effect=forbidden_action), \
                patch('socket.socket', side_effect=forbidden_action), \
                patch.object(os, 'environ', NoEnvironment()), \
                patch('os.getenv', side_effect=forbidden_action), \
                patch('os.mkdir', side_effect=forbidden_action), \
                patch('os.open', side_effect=forbidden_action), \
                patch('builtins.open', registry_only_open), patch('io.open', registry_only_open), \
                patch('builtins.__import__', checked_import):
            exec(code, namespace)
            plan = namespace['build_provider_plan'](namespace['load_registry'](FIXTURE))
        self.assertEqual(reads, [FIXTURE])
        self.assertEqual(plan['provider_count'], 5)
        self.assertEqual(plan['network_requests'], 0)
        self.assertFalse(plan['live_run_authorized'])


if __name__ == '__main__':
    unittest.main()
