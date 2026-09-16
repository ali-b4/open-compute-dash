"""Rebuild a side-by-side HTML report from a saved run, without any API calls."""

import argparse
import html
import json
from pathlib import Path

if __package__:
    from .measurements import normalize
    from .provider_config import PROVIDERS, PROVIDER_LABELS
else:
    from measurements import normalize
    from provider_config import PROVIDERS, PROVIDER_LABELS


def metrics_html(result):
    if 'metrics' not in result:
        normalize(result)
    rows = []
    labels = {'ttft_seconds': 'Time to first token', 'total_latency_seconds': 'Total latency',
              'output_tokens_per_second': 'Output throughput', 'input_price_per_1m': 'Input price',
              'output_price_per_1m': 'Output price'}
    for key, item in {**result['metrics'], **result['metadata']}.items():
        value = item['value']
        if value is None:
            display = 'Unavailable'
        elif isinstance(value, float):
            display = f'{value:.8g}'
        elif isinstance(value, (dict, list)):
            display = json.dumps(value, ensure_ascii=False)
        else:
            display = str(value)
        unit = item.get('unit') or ''
        detail = item.get('reason') or item['source']
        if item.get('note'):
            detail += '. ' + item['note']
        rows.append('<tr><th>' + html.escape(labels.get(key, key.replace('_', ' ').capitalize())) +
                    '</th><td>' + html.escape(display + ' ' + unit) + '<small>' + html.escape(detail) + '</small></td></tr>')
    return '<details class="metrics"><summary>Metrics</summary><table>' + ''.join(rows) + '</table></details>'


def render_report(directory: Path) -> Path:
    columns = []
    for provider in PROVIDERS:
        path = directory / f"{provider}.json"
        if path.exists():
            result = json.loads(path.read_text(encoding="utf-8"))
            success = result["success"]
            state = "Success" if success else "Failed"
            response = result.get("response") or {}
            status = response.get("status_code", "No HTTP response")
            summary = html.escape(f"{state} · {status} · {result['total_latency_seconds']}s")
            model = html.escape(result["provider_model_id"])
            body = f'<p class="{"ok" if success else "failed"}">{summary}</p><p class="model">{model}</p>'
            body += metrics_html(result)
            if result.get("stream"):
                body += '<details><summary>Assembled output</summary><pre>' + html.escape(result["stream"]["content"]) + '</pre></details>'
            if result.get("error"):
                body += '<h2>Error</h2><pre>' + html.escape(json.dumps(result["error"], indent=2)) + '</pre>'
            body += '<h2>Response JSON</h2><pre>' + html.escape(json.dumps(result["response"], indent=2, ensure_ascii=False)) + '</pre>'
            body += '<details><summary>Request JSON</summary><pre>' + html.escape(json.dumps(result["request"], indent=2, ensure_ascii=False)) + '</pre></details>'
        else:
            body = '<p class="model">Not selected for this run</p>'
        columns.append(f'<section><h1>{PROVIDER_LABELS[provider]}</h1>{body}</section>')
    page = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Provider request comparison</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#182434;font:15px system-ui,sans-serif}
header{padding:20px 24px;border-bottom:1px solid #dbe1e8}header strong{font-size:22px}header p{margin-bottom:0;color:#536275}
main{display:grid;grid-template-columns:repeat(PROVIDER_COUNT,minmax(0,1fr));gap:14px;padding:18px;min-width:1200px}
section{display:flex;flex-direction:column;background:white;border:1px solid #dbe1e8;border-radius:10px;padding:18px;min-width:0}
h1{font-size:21px;margin:0}h2,summary{font-size:14px;font-weight:600}summary{cursor:pointer;padding:12px 0}
pre{font:12px/1.6 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7fa;border-radius:6px;padding:12px;max-height:65vh;overflow:auto}
table{border-collapse:collapse;width:100%;font-size:12px}th,td{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid #e4e8ed;overflow-wrap:anywhere}th{width:40%}small{display:block;color:#536275;margin-top:4px}.metrics{max-height:65vh;overflow:auto}.model{min-height:32px;color:#536275;overflow-wrap:anywhere;font-size:12px}.ok{color:#087345}.failed{color:#b42318}
</style></head><body><header><strong>Provider request comparison</strong>
<p>RUN_ID · Streaming mode is recorded in Request JSON. Elapsed time includes the full request. Expand Metrics for measurements, sources, and unavailable reasons.</p>
</header><main>COLUMNS</main></body></html>'''
    page = page.replace("PROVIDER_COUNT", str(len(PROVIDERS)))
    page = page.replace("RUN_ID", html.escape(directory.name)).replace("COLUMNS", "".join(columns))
    output = directory / "report.html"
    output.write_text(page, encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    if not any((args.run_directory / f"{name}.json").exists() for name in PROVIDERS):
        parser.error("Directory contains no saved provider results")
    print(render_report(args.run_directory))
