"""Run isolated live diagnostics; expected request failures are validation passes."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import uuid
import webbrowser

from manual_request import ROOT, load_dotenv, probe
from provider_config import PROVIDERS
from render_report import render_report

CASES = ('invalid_auth', 'invalid_model', 'invalid_parameter', 'timeout', 'mixed')


def assess(result, case, expected_failure):
    status = (result.get('response') or {}).get('status_code')
    error = result.get('error') or {}
    if not expected_failure:
        passed = result['success']
        expected = 'Successful control request'
    elif case == 'timeout':
        passed = not result['success'] and 'timed out' in error.get('message', '').lower()
        expected = 'Local timeout (not a provider outage)'
    else:
        codes = {401, 403} if case in {'invalid_auth', 'mixed'} else {400, 403, 404, 422}
        passed = not result['success'] and status in codes
        expected = 'Authentication rejected' if case in {'invalid_auth', 'mixed'} else 'Invalid request rejected; inspect provider details'
    metrics = result.get('metrics', {})
    required_metrics = {'ttft_seconds', 'total_latency_seconds', 'output_tokens_per_second',
                        'input_tokens', 'output_tokens', 'reasoning_tokens', 'input_price_per_1m',
                        'output_price_per_1m', 'input_cost', 'output_cost', 'request_cost',
                        'success', 'http_status', 'error_type', 'error_message'}
    required_metadata = {'provider', 'model', 'provider_model_id', 'returned_model_id', 'pricing',
                         'rate_limits', 'region', 'version', 'context_window', 'quantization'}
    complete = required_metrics <= metrics.keys() and required_metadata <= result.get('metadata', {}).keys()
    entries = list(metrics.values()) + list(result.get('metadata', {}).values())
    complete = complete and all({'value', 'unit', 'source', 'reason'} <= item.keys() for item in entries)
    complete = complete and all(item.get('reason') for item in entries if item.get('value') is None)
    complete = complete and metrics.get('success', {}).get('value') == result['success']
    complete = complete and metrics.get('http_status', {}).get('value') == status
    if expected_failure:
        complete = complete and bool(error.get('type') and error.get('message'))
    return dict(passed=bool(passed and complete), expected=expected, http_status=status,
                error_type=error.get('type'), record_complete=bool(complete))


def validate(output, providers, cases, modes, timeout):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for streaming in modes:
        mode = 'streaming' if streaming else 'non-streaming'
        for case in cases:
            directory = output / f'{mode}-{case}'
            directory.mkdir()
            with ThreadPoolExecutor(max_workers=len(providers)) as pool:
                futures = {}
                for provider in providers:
                    diagnostic = ('invalid_auth' if provider == providers[0] else None) if case == 'mixed' else case
                    futures[pool.submit(probe, provider, 'Reply with exactly: hello', timeout, streaming,
                                        diagnostic=diagnostic)] = (provider, diagnostic is not None)
                for future in as_completed(futures):
                    provider, expected_failure = futures[future]
                    result = future.result()
                    check = assess(result, case, expected_failure)
                    result['validation'] = {**check, 'case': case, 'exclude_from_benchmark': True}
                    (directory / f'{provider}.json').write_text(json.dumps(result, indent=2)+'\n')
                    rows.append(dict(provider=provider, mode=mode, case=case,
                                     report=f'{directory.name}/report.html', **check))
                    print(f"{mode} {case} {provider}: {'PASS' if check['passed'] else 'REVIEW'}", flush=True)
            render_report(directory)
            save_summary(output, rows)
    return rows


def save_summary(output, rows):
    summary = {'passed': sum(row['passed'] for row in rows), 'total': len(rows), 'checks': rows}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    table = []
    for row in rows:
        values = ['PASS' if row['passed'] else 'REVIEW', row['mode'], row['case'], row['provider'],
                  str(row['http_status'] or 'No HTTP response'), row['expected']]
        table.append('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in values)+
                     '<td><a href="'+html.escape(row['report'])+'">Details</a></td></tr>')
    (output / 'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Failure validation</title><style>body{font:16px system-ui;margin:32px;color:#182434}
table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}</style>
<h1>Failure validation</h1><p>PASS means the expected behavior occurred. A deliberately failed request
should show Failed in its detailed report. REVIEW means the observed result needs investigation.</p>
<p>Timeouts are deliberately local; they do not demonstrate provider outages. These diagnostic records
must not be included in normal benchmark comparisons.</p>'''+f'<h2>{summary["passed"]} / {summary["total"]} checks passed</h2>'+ 
        '<table><tr><th>Check</th><th>Mode</th><th>Case</th><th>Provider</th><th>HTTP</th><th>Expected</th><th>Report</th></tr>'+''.join(table)+'</table></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--providers', nargs='+', choices=PROVIDERS, default=list(PROVIDERS))
    parser.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    parser.add_argument('--mode', choices=('both','streaming','non-streaming'), default='both')
    parser.add_argument('--timeout', type=float, default=45)
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    if not 0 < args.timeout < float('inf'):
        parser.error('--timeout must be a positive finite number')
    selected = list(dict.fromkeys(args.providers))
    if 'mixed' in args.cases and len(selected) < 2:
        parser.error('mixed requires at least two providers')
    load_dotenv()
    missing = [p for p in selected if not os.getenv(f'{p.upper()}_API_KEY')]
    if missing:
        parser.error('Configure API keys before validation: '+', '.join(missing))
    modes = [False, True] if args.mode == 'both' else [args.mode == 'streaming']
    output = ROOT / 'results' / 'validation' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    rows = validate(output, selected, list(dict.fromkeys(args.cases)), modes, args.timeout)
    print(f'Report: {output / "index.html"}')
    if args.open:
        webbrowser.open((output/'index.html').as_uri())
    raise SystemExit(0 if all(row['passed'] for row in rows) else 1)

if __name__ == '__main__':
    main()
