"""Offline token accounting for saved simple text chats; optional Venice diagnostics.

Requires the optional tokenizers and jinja2 packages, not needed by the benchmark.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import importlib.metadata
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1]


def audit_record(result, count, template):
    if result.get('model') != 'qwen/qwen3.8-27b':
        return {'provider': result['provider'], 'available': False, 'reason': 'Audit tokenizer is only for the fixed Qwen model.'}
    body = (result.get('response') or {}).get('body')
    if not result.get('success') or not isinstance(body, dict):
        return {'provider': result['provider'], 'available': False, 'reason': 'Request failed or response is not an object.'}
    choices = body.get('choices') or []
    if len(choices) != 1 or not isinstance(choices[0].get('message'), dict):
        return {'provider': result['provider'], 'available': False, 'reason': 'Requires one assembled assistant message.'}
    message = choices[0]['message']
    reason = message.get('reasoning_content') or message.get('reasoning')
    answer = message.get('content')
    if not isinstance(reason, str) or not isinstance(answer, str) or message.get('tool_calls'):
        return {'provider': result['provider'], 'available': False, 'reason': 'Requires visible reasoning and text answer without tool calls.'}
    payload = result['request']['json']
    if payload.get('tools') or any(m.get('role') != 'user' or not isinstance(m.get('content'), str) for m in payload.get('messages', [])):
        return {'provider': result['provider'], 'available': False, 'reason': 'This audit supports user-only text prompts without tools.'}
    usage = body.get('usage') or {}
    # The public template puts the opening think marker in the prompt.
    # This hypothesis reconstructs the generated closing marker and end marker.
    reconstructed = reason + '</think>' + answer + '<|im_end|>'
    local_output = count(reconstructed)
    public_prompt = template.render(messages=payload['messages'], add_generation_prompt=True,
                                    reasoning_effort=payload.get('reasoning_effort', 'xhigh'))
    reported_input, reported_output = usage.get('prompt_tokens'), usage.get('completion_tokens')
    local_input = count(public_prompt)
    return dict(provider=result['provider'], available=True,
                streaming=payload.get('stream', False), provider_model_id=result['provider_model_id'],
                reasoning_effort=payload.get('reasoning_effort', 'provider default'),
                venice_system_prompt=(payload.get('venice_parameters') or {}).get('include_venice_system_prompt'),
                reported_input_tokens=reported_input, public_template_input_tokens=local_input,
                input_difference=reported_input-local_input if reported_input is not None else None,
                reported_output_tokens=reported_output, visible_answer_tokens=count(answer),
                visible_reasoning_tokens=count(reason), reconstructed_output_tokens=local_output,
                output_matches=local_output == reported_output if reported_output is not None else None,
                reported_reasoning_tokens=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
                reconstructed_output=reconstructed, public_template_prompt=public_prompt,
                basis='Local reconstruction, not an authoritative provider tokenizer trace.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directories', nargs='+', type=Path)
    parser.add_argument('--tokenizer-directory', type=Path, default=ROOT/'results/accounting/tokenizer')
    parser.add_argument('--collect-venice', action='store_true', help='Also make four isolated Venice requests to investigate defaults')
    args = parser.parse_args()
    try:
        from tokenizers import Tokenizer
        from jinja2.sandbox import ImmutableSandboxedEnvironment
    except ImportError:
        parser.error('Optional audit tools required: install tokenizers and jinja2 in an isolated environment; see notes/token-accounting.md')
    manifest = json.loads((args.tokenizer_directory/'manifest.json').read_text())
    for name, info in manifest['files'].items():
        if hashlib.sha256((args.tokenizer_directory/name).read_bytes()).hexdigest() != info['sha256']:
            parser.error(f'Tokenizer file checksum mismatch: {name}')
    tokenizer = Tokenizer.from_file(str(args.tokenizer_directory/'tokenizer.json'))
    count = lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids)
    env = ImmutableSandboxedEnvironment()
    def fail(message):
        raise ValueError(message)
    env.globals['raise_exception'] = fail
    template = env.from_string((args.tokenizer_directory/'chat_template.jinja').read_text())
    inputs = []
    for directory in args.run_directories:
        paths = sorted(directory.glob('*.json'))
        if not paths:
            parser.error(f'No records in {directory}')
        inputs.extend(paths)
    output = ROOT/'results/accounting'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    if args.collect_venice:
        from manual_request import load_dotenv, probe
        from render_report import render_report
        load_dotenv()
        for case in (None, 'reasoning_medium', 'reasoning_xhigh', 'system_prompt_on'):
            directory = output/(case or 'baseline');directory.mkdir()
            record = probe('venice','Reply with exactly: hello',45,diagnostic=case)
            record['accounting_diagnostic'] = {'case':case or 'baseline', 'exclude_from_benchmark':True}
            path=directory/'venice.json';path.write_text(json.dumps(record,indent=2)+'\n')
            render_report(directory);inputs.append(path)
            print(f"Venice {case or 'baseline'}: {'OK' if record['success'] else 'FAILED'}", flush=True)
    rows=[]
    for path in inputs:
        row=audit_record(json.loads(path.read_text()),count,template)
        row['record_path']=str(path.resolve().relative_to(ROOT))
        row['record_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(row)
    report=dict(tokenizer=manifest, tool_versions={n:importlib.metadata.version(n) for n in ('tokenizers','jinja2')},
                reconstruction='visible reasoning + </think> + visible answer + <|im_end|>', observations=rows)
    (output/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    table=[]
    for r in rows:
        values=[r['provider'],r['record_path'],r.get('reported_input_tokens'),r.get('public_template_input_tokens'),
                r.get('input_difference'),r.get('reported_output_tokens'),r.get('visible_reasoning_tokens'),
                r.get('visible_answer_tokens'),r.get('reconstructed_output_tokens'),r.get('output_matches',r.get('reason'))]
        table.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in values)+'</tr>')
    (output/'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><title>Token accounting audit</title>
<style>body{font:15px system-ui;margin:24px}table{border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}td{overflow-wrap:anywhere;max-width:320px}</style>
<h1>Token accounting audit</h1><p>Local counts use the public Qwen tokenizer. A matching reconstruction supports reasoning inclusion for these observations;
it does not prove the provider uses this exact tokenizer or reveal its hidden input template. Original records and benchmark metrics are unchanged.</p>
<p>Reconstructed output includes visible reasoning, answer, closing thinking marker, and end marker. These diagnostics are excluded from benchmark comparisons.</p>
<table><tr><th>Provider</th><th>Saved record</th><th>Reported input</th><th>Public-template input</th><th>Difference</th><th>Reported output</th><th>Reasoning text</th><th>Answer text</th><th>Reconstructed output</th><th>Output matches</th></tr>'''+''.join(table)+'</table></html>')
    print(f'Audit: {output}/index.html')

if __name__ == '__main__':
    main()
