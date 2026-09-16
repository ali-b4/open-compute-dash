"""Normalized metrics with explicit provenance and unavailable reasons."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def metric(value, source, reason=None, unit=None):
    return dict(value=value, source=source if value is not None else 'unavailable',
                reason=reason if value is None else None, unit=unit)


def normalize(result):
    response = result.get('response') or {}
    body = response.get('body') or {}
    if not isinstance(body, dict):
        body = {}
    usage = body.get('usage') or {}
    config = json.loads((ROOT / 'config/pricing.json').read_text()).get(result['provider'], {})
    if config.get('provider_model_id') != result.get('provider_model_id'):
        config = {}
    reported = lambda v, unit=None: metric(v, 'provider-reported', 'Not supplied by provider.', unit)
    tokens = lambda key: usage.get(key) if isinstance(usage.get(key), int) and usage[key] >= 0 else None
    inp, out = tokens('prompt_tokens'), tokens('completion_tokens')
    stream = result.get('stream', {})
    first, last = stream.get('first_token_seconds'), stream.get('last_token_seconds')
    streaming = result.get('request', {}).get('json', {}).get('stream', False)
    interval = last - first if first is not None and last is not None else 0
    throughput = out / interval if result['success'] and out is not None and interval > 0 else None
    pi, po = config.get('input_per_1m_tokens'), config.get('output_per_1m_tokens')
    input_cost = inp * pi / 1e6 if inp is not None and pi is not None else None
    cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens')
    cache_price = config.get('cache_input_per_1m_tokens')
    if input_cost is not None and cached and cache_price is not None and 0 <= cached <= inp:
        input_cost = ((inp - cached) * pi + cached * cache_price) / 1e6
    output_cost = out * po / 1e6 if out is not None and po is not None else None
    cost = input_cost + output_cost if input_cost is not None and output_cost is not None else None
    if cost is not None:
        cost = max(cost, config.get('minimum_request_cost_usd', 0))
    headers = {k.lower(): v for k,v in response.get('headers', {}).items()}
    m = {
        'ttft_seconds': metric(first, 'measured', 'No generated content received.' if streaming else 'Non-streaming does not expose first-token arrival.', 's'),
        'total_latency_seconds': metric(result.get('total_latency_seconds') if result.get('request_sent', True) else None, 'measured', 'Request was not sent.', 's'),
        'output_tokens_per_second': metric(throughput, 'estimated', 'Requires a successful stream, usage, and a positive generation interval.', 'tokens/s'),
        'input_tokens': reported(inp, 'tokens'), 'output_tokens': reported(out, 'tokens'),
        'reasoning_tokens': reported((usage.get('completion_tokens_details') or {}).get('reasoning_tokens'), 'tokens'),
        'input_price_per_1m': metric(pi, 'provider-reported', 'No verified price for this model.', 'USD/1M tokens'),
        'output_price_per_1m': metric(po, 'provider-reported', 'No verified price for this model.', 'USD/1M tokens'),
        'input_cost': metric(input_cost, 'estimated', 'Usage or verified pricing unavailable.', 'USD'),
        'output_cost': metric(output_cost, 'estimated', 'Usage or verified pricing unavailable.', 'USD'),
        'request_cost': metric(cost, 'estimated', 'Usage or verified pricing unavailable.', 'USD'),
        'success': metric(result['success'], 'measured'),
        'http_status': reported(response.get('status_code')),
        'error_type': metric((result.get('error') or {}).get('type'), 'measured', 'No error.'),
        'error_message': metric((result.get('error') or {}).get('message'), 'measured', 'No error.'),
    }
    m['request_cost']['note'] = config.get('cost_basis')
    m['output_tokens']['note'] = 'Provider completion_tokens retained as total output; reasoning detail is a subset, never added again. Separate reasoning counts may be unavailable.'
    m['output_tokens_per_second']['note'] = 'Completion tokens divided by first-to-last content/reasoning chunk interval; chunk buffering can inflate this estimate.'
    result['metrics'] = m
    result['metadata'] = {
        'provider': metric(result['provider'], 'configured'),
        'model': metric(result.get('model'), 'configured', 'Not recorded.'),
        'provider_model_id': metric(result['provider_model_id'], 'configured'),
        'returned_model_id': reported(body.get('model')),
        'pricing': metric(config or None, 'provider-reported', 'No verified model pricing.'),
        'rate_limits': reported({k:v for k,v in headers.items()
                                 if 'ratelimit' in k or k == 'retry-after'
                                 or k.startswith(('x-chutes-rl-', 'x-chutes-quota-'))} or None),
        'region': reported(headers.get('x-region')),
        'version': reported(headers.get('x-venice-version') or body.get('system_fingerprint')),
        'context_window': reported(config.get('context_window'), 'tokens'),
        'quantization': reported(config.get('quantization')),
    }
    return result
