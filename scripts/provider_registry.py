"""Validate v0.5 provider configuration and select endpoints entirely offline.

This module deliberately does not import inherited transports, pricing refresh,
or credential loaders. A selection is not an approved collection or live run.
"""

from copy import deepcopy
from datetime import datetime
import ipaddress
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit


DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / 'config/providers.json'
REGISTRY_VERSION = 'provider-registry-v1'
EVIDENCE_FIELDS = {
    'access', 'streaming', 'streaming_usage', 'non_thinking',
    'context_window_tokens', 'cache_policy', 'structured_output', 'tool_calls',
}
BOOLEAN_EVIDENCE = EVIDENCE_FIELDS - {'context_window_tokens', 'cache_policy'}
STATUSES = {'verification_pending', 'active', 'access_pending', 'disabled'}
EVIDENCE_STATUSES = {'unknown', 'configured', 'documented', 'provider_reported', 'measured', 'estimated'}
PROVIDER_FIELDS = {
    'provider_id', 'display_name', 'enabled', 'status', 'adapter_type',
    'secret_env_var', 'endpoint_url', 'model_id', 'serving_variant', 'evidence', 'pricing',
}


def _fields(value, required, allowed, label):
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - allowed:
        raise ValueError(f'{label}: missing required fields or unsupported fields.')


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f'{label}: expected nonempty text without control characters or surrounding whitespace.')


def _identifier(value, pattern, label):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError(f'{label}: invalid identifier format.')


def _evidence(value, label):
    fields = {'value', 'status', 'source', 'checked_at', 'reason'}
    _fields(value, fields, fields, label)
    if not isinstance(value['status'], str) or value['status'] not in EVIDENCE_STATUSES:
        raise ValueError(f'{label}: unsupported evidence status.')
    _text(value['reason'], f'{label}.reason')
    if value['status'] == 'unknown':
        if any(value[key] is not None for key in ('value', 'source', 'checked_at')):
            raise ValueError(f'{label}: unknown evidence requires null value, source, and checked_at.')
        return
    observed = value['value']
    if observed is None or type(observed) not in (str, bool, int, float):
        raise ValueError(f'{label}: known evidence requires a scalar value.')
    if isinstance(observed, str):
        _text(observed, f'{label}.value')
    if type(observed) in (int, float):
        try:
            valid = math.isfinite(observed) and observed >= 0
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f'{label}: numeric evidence must be finite and nonnegative.')
    _text(value['source'], f'{label}.source')
    if not isinstance(value['checked_at'], str):
        raise ValueError(f'{label}: known evidence needs an ISO date or timestamp.')
    try:
        datetime.fromisoformat(value['checked_at'].replace('Z', '+00:00'))
    except ValueError:
        raise ValueError(f'{label}: known evidence needs an ISO date or timestamp.') from None


def _endpoint(value):
    _text(value, 'endpoint_url')
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        valid_host = False
        if host:
            try:
                ipaddress.ip_address(host)
                valid_host = True
            except ValueError:
                ascii_host = host.encode('idna').decode('ascii').removesuffix('.')
                valid_host = len(ascii_host) <= 253 and all(
                    re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part)
                    for part in ascii_host.split('.')
                )
        valid = (parsed.scheme == 'https' and valid_host and parsed.username is None
                 and parsed.password is None and not parsed.query and not parsed.fragment
                 and parsed.port != 0 and '\\' not in value and not any(c.isspace() for c in value))
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise ValueError('endpoint_url: use a valid HTTPS host without embedded credentials, query, fragment, or backslashes.')


def _pricing(value):
    fields = {'config_file', 'config_key', 'status', 'reason'}
    _fields(value, fields, fields, 'pricing')
    _text(value['reason'], 'pricing.reason')
    if value['status'] == 'unknown':
        if value['config_file'] is not None or value['config_key'] is not None:
            raise ValueError('pricing: unknown pricing requires null configuration references.')
    elif value['status'] == 'historical_unverified':
        reference = value['config_file']
        _text(reference, 'pricing.config_file')
        if not re.fullmatch(r'config/[A-Za-z0-9_.-]+\.json', reference):
            raise ValueError('pricing.config_file: expected a JSON filename inside config/.')
        _identifier(value['config_key'], r'[a-z][a-z0-9_]*', 'pricing.config_key')
    else:
        raise ValueError('pricing: expected unknown or historical_unverified; this registry does not verify prices.')


def validate_registry(registry):
    """Validate structure and evidence without opening any referenced files."""
    fields = {'schema_version', 'canonical_model_family', 'synthetic', 'providers'}
    _fields(registry, fields, fields, 'registry')
    if registry['schema_version'] != REGISTRY_VERSION:
        raise ValueError('registry: unsupported schema_version.')
    _text(registry['canonical_model_family'], 'canonical_model_family')
    if type(registry['synthetic']) is not bool:
        raise ValueError('registry.synthetic: expected a boolean.')
    if not isinstance(registry['providers'], list):
        raise ValueError('registry.providers: expected a list.')
    seen = set()
    for provider in registry['providers']:
        _fields(provider, {'provider_id', 'display_name', 'enabled', 'status'}, PROVIDER_FIELDS, 'provider')
        identifier = provider['provider_id']
        _identifier(identifier, r'[a-z][a-z0-9_]*', 'provider_id')
        if identifier in seen:
            raise ValueError('registry: duplicate provider_id.')
        seen.add(identifier)
        _text(provider['display_name'], 'display_name')
        if type(provider['enabled']) is not bool:
            raise ValueError('provider.enabled: expected a boolean.')
        if not isinstance(provider['status'], str) or provider['status'] not in STATUSES:
            raise ValueError('provider.status: unsupported lifecycle status.')
        if provider['enabled'] and provider['status'] in {'access_pending', 'disabled'}:
            raise ValueError('provider: access_pending or disabled entries cannot be enabled.')
        if provider['enabled']:
            _fields(provider, PROVIDER_FIELDS, PROVIDER_FIELDS, 'enabled provider')
        # Disabled placeholders can omit unknown integration fields; validate any supplied values.
        for key in ('adapter_type', 'secret_env_var', 'endpoint_url', 'model_id', 'serving_variant', 'evidence', 'pricing'):
            if provider.get(key) is None:
                if provider['enabled']:
                    raise ValueError(f'enabled provider: {key} cannot be null.')
                continue
            value = provider[key]
            if key == 'adapter_type' and value != 'openai_chat_completions':
                raise ValueError('adapter_type: unsupported adapter; add a reviewed adapter before selecting it.')
            elif key == 'secret_env_var':
                _identifier(value, r'[A-Z][A-Z0-9_]*', 'secret_env_var')
            elif key == 'endpoint_url':
                _endpoint(value)
            elif key == 'model_id':
                _text(value, 'model_id')
            elif key == 'serving_variant':
                _evidence(value, 'serving_variant')
                if value['value'] is not None and not isinstance(value['value'], str):
                    raise ValueError('serving_variant: expected a text label or unknown evidence.')
            elif key == 'evidence':
                _fields(value, EVIDENCE_FIELDS, EVIDENCE_FIELDS, 'evidence')
                for capability, evidence in value.items():
                    _evidence(evidence, f'evidence.{capability}')
                    observed = evidence['value']
                    if observed is None:
                        continue
                    if capability in BOOLEAN_EVIDENCE and type(observed) is not bool:
                        raise ValueError(f'evidence.{capability}: expected a boolean value.')
                    if capability == 'context_window_tokens' and (type(observed) is not int or observed <= 0):
                        raise ValueError('evidence.context_window_tokens: expected a positive integer.')
                    if capability == 'cache_policy' and not isinstance(observed, str):
                        raise ValueError('evidence.cache_policy: expected text.')
            elif key == 'pricing':
                _pricing(value)
    return registry


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('registry: duplicate JSON field; retain exactly one value for each field.')
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError('registry: nonfinite JSON numbers are not allowed.')


def load_registry(path=None):
    """Read just this registry. Never load credentials, referenced pricing, or adapters."""
    try:
        data = json.loads(Path(path or DEFAULT_REGISTRY).read_text(encoding='utf-8'),
                          object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (OSError, UnicodeError):
        raise ValueError('Cannot read registry. Supply a readable UTF-8 JSON file.') from None
    except (json.JSONDecodeError, RecursionError):
        raise ValueError('Invalid registry JSON. Check its syntax and nesting.') from None
    return validate_registry(data)


def build_provider_plan(registry, selected=None):
    """Create an offline selection, not a workload schedule or spend reservation."""
    validate_registry(registry)
    by_id = {provider['provider_id']: provider for provider in registry['providers']}
    if selected is None:
        providers = [provider for provider in registry['providers'] if provider['enabled']]
    else:
        if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected):
            raise ValueError('Provider selection must be a list of provider IDs.')
        if len(set(selected)) != len(selected):
            raise ValueError('Provider selection contains duplicates.')
        if any(identifier not in by_id for identifier in selected):
            raise ValueError('Unknown provider selected. Inspect the registry to see configured IDs.')
        providers = [by_id[identifier] for identifier in selected]
        if any(not provider['enabled'] for provider in providers):
            raise ValueError('A selected provider is disabled or awaiting access; it cannot enter this selection.')
    return {
        'schema_version': 'provider-selection-v1',
        'registry_version': registry['schema_version'],
        'canonical_model_family': registry['canonical_model_family'],
        'synthetic': registry['synthetic'],
        'purpose': 'offline_registry_review',
        'provider_count': len(providers),
        'providers': deepcopy(providers),
        'required_secret_variables': list(dict.fromkeys(provider['secret_env_var'] for provider in providers)),
        'excluded_providers': [
            {key: provider[key] for key in ('provider_id', 'display_name', 'status')}
            for provider in registry['providers'] if not provider['enabled']
        ],
        'network_requests': 0,
        'live_run_authorized': False,
    }
