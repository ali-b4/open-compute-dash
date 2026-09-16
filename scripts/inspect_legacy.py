"""Inspect saved v0.1 records offline without rewriting them or recalculating metrics."""

import argparse
import json
import math
from pathlib import Path
import re


# Keep definitions independent of the current measurement code and pricing files.
# Summary rows lost metric provenance; these are the original v0.1 definitions.
METRICS = {
    'ttft_seconds': ('s', 'Time to first nonempty content OR reasoning chunk, not first visible answer token.'),
    'total_latency_seconds': ('s', 'Elapsed full request time, unavailable when the request was not sent.'),
    'output_tokens_per_second': ('tokens/s', 'Legacy estimate: provider completion tokens divided by the first-to-last content/reasoning chunk interval; buffering can inflate it.'),
    'input_tokens': ('tokens', 'Provider-reported prompt tokens.'),
    'output_tokens': ('tokens', 'Provider-reported completion tokens, including any reported reasoning subset.'),
    'reasoning_tokens': ('tokens', 'Provider-reported reasoning subset; never added to output tokens.'),
    'input_price_per_1m': ('USD/1M tokens', 'Saved input price; current pricing is never consulted.'),
    'output_price_per_1m': ('USD/1M tokens', 'Saved output price; current pricing is never consulted.'),
    'input_cost': ('USD', 'Saved estimated input cost, including any legacy cache adjustment.'),
    'output_cost': ('USD', 'Saved estimated output cost.'),
    'request_cost': ('USD', 'Saved estimated request cost, including any legacy minimum; not a verified bill.'),
}
LABEL = 'Legacy v0.1 observations — NOT APS data or provider rankings'


def _label(value, name, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}', value):
        raise ValueError(f'{name} must be a short identifier, without spaces or control characters.')
    return value


def _boolean(value, name):
    if value is not None and type(value) is not bool:
        raise ValueError(f'{name} must be true, false, or null.')
    return value


def _number(value, name):
    if value is not None and (type(value) not in (int, float) or value < 0
                              or (type(value) is float and not math.isfinite(value))):
        raise ValueError(f'{name} must be a finite nonnegative number or null.')
    return value


def _observation(record, normalized):
    if not isinstance(record, dict):
        raise ValueError('Every observation must be a JSON object.')
    saved = record['metrics'] if normalized else record
    if not isinstance(saved, dict):
        raise ValueError('A normalized observation must have a metrics object.')

    def value(key):
        if not normalized or key not in saved:
            return saved.get(key)
        item = saved[key]
        if not isinstance(item, dict) or 'value' not in item:
            raise ValueError(f'Normalized {key} must contain a value field.')
        return item['value']

    success = value('success')
    if normalized and 'success' not in saved:
        success = record.get('success')
    finish = record.get('finish_reason')
    if normalized and finish is None:
        response = record.get('response')
        body = response.get('body') if isinstance(response, dict) else None
        choices = body.get('choices') if isinstance(body, dict) else None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            finish = choices[0].get('finish_reason')
    return {
        'provider': _label(record.get('provider'), 'provider'),
        'success': _boolean(success, 'success'),
        'finish_reason': _label(finish, 'finish_reason', optional=True),
        **{key: _number(value(key), key) for key in METRICS},
    }


def inspect_document(document):
    """Return only safe saved fields. Do not normalize, follow record links, or mutate input."""
    if not isinstance(document, dict):
        raise ValueError('Expected a legacy summary object or a normalized observation object.')
    if 'observations' in document:
        rows = document['observations']
        if not isinstance(rows, list):
            raise ValueError('A legacy summary must contain an observations list.')
        kind = 'summary'
        observations = [_observation(row, normalized=False) for row in rows]
    elif 'provider' in document and 'metrics' in document:
        kind = 'normalized_observation'
        observations = [_observation(document, normalized=True)]
    else:
        raise ValueError('Unsupported record: provide a legacy summary with observations or a normalized observation with provider and metrics.')

    counts = {
        'saved': len(observations),
        'successful': sum(row['success'] is True for row in observations),
        'failed': sum(row['success'] is False for row in observations),
        'unknown_success': sum(row['success'] is None for row in observations),
    }
    expected = document.get('expected_observations') if kind == 'summary' else None
    if expected is not None and (type(expected) is not int or expected < len(observations)):
        raise ValueError('expected_observations must be an integer at least as large as the saved observation count.')
    for field, count in [('saved_observations', counts['saved']), ('successful_observations', counts['successful'])]:
        if kind == 'summary' and field in document:
            if type(document[field]) is not int or document[field] != count:
                raise ValueError(f'{field} does not match the observations; inspect the original record.')
    return {
        'label': LABEL,
        'record_kind': kind,
        'synthetic_fixture': document.get('_synthetic_fixture') is True,
        'counts': {**counts, 'expected': expected},
        'providers': sorted({row['provider'] for row in observations}),
        'note': 'Saved values only. Null or absent means unavailable, never zero. No metrics or costs are recalculated.',
        'metric_definitions': {key: {'unit': unit, 'meaning': meaning} for key, (unit, meaning) in METRICS.items()},
        'observations': observations,
    }


def read_record(path):
    """Read exactly the supplied JSON file; no directories, outputs, secrets, or network."""
    try:
        document = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError):
        raise ValueError('Cannot read the file. Provide a readable UTF-8 legacy JSON file.') from None
    except (json.JSONDecodeError, RecursionError):
        raise ValueError('Invalid JSON. Provide a saved legacy summary or normalized observation JSON file.') from None
    return inspect_document(document)


def format_text(report):
    def display(value, unit=''):
        return 'Unavailable' if value is None else f'{value}{" " + unit if unit else ""}'

    counts = report['counts']
    lines = [report['label']]
    if report['synthetic_fixture']:
        lines.append('SYNTHETIC TEST FIXTURE — not a real provider run')
    lines.extend([
        f"Observations: {counts['saved']} saved; {display(counts['expected'])} expected. API results: {counts['successful']} successful, {counts['failed']} failed, {counts['unknown_success']} unknown. Providers: {', '.join(report['providers']) or 'None'}.",
        'Saved values only. Unavailable means missing, not zero. Costs are saved estimates, not verified bills.',
    ])
    for index, row in enumerate(report['observations'], 1):
        state = 'API success' if row['success'] is True else 'API failed' if row['success'] is False else 'API success unknown'
        lines.extend([
            f"\n{index}. {row['provider']} — {state}; finish reason: {display(row['finish_reason'])}",
            f"  First-content time: {display(row['ttft_seconds'], 's')}; total time: {display(row['total_latency_seconds'], 's')}",
            f"  Legacy output speed: {display(row['output_tokens_per_second'], 'tokens/s')}; saved estimated cost: {display(row['request_cost'], 'USD')}",
        ])
    lines.extend([
        '\nAPI success does not guarantee a final answer.',
        'First-content time includes reasoning chunks. Legacy output speed uses provider-reported completion tokens divided by the first-to-last content/reasoning interval; buffering can inflate it.',
        'Use --json for additional saved metrics and their original definitions.',
    ])
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path, help='Saved v0.1 summary.json or normalized observation JSON file')
    parser.add_argument('--json', action='store_true', help='Print the same safe information as JSON')
    args = parser.parse_args(argv)
    try:
        report = read_record(args.path)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) if args.json else format_text(report))


if __name__ == '__main__':
    main()
