"""Send the same prompt concurrently to selected providers and save an HTML log."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid
import webbrowser

if __package__:
    from .render_report import render_report
    from .measurements import normalize
    from .streaming import read_stream
    from .provider_config import MODEL, PROVIDERS
else:
    from render_report import render_report
    from measurements import normalize
    from streaming import read_stream
    from provider_config import MODEL, PROVIDERS

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv() -> None:
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if value[:1] in {"'", '"'} and value[-1:] == value[:1]:
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)


def probe(provider: str, prompt: str, timeout: float, streaming: bool = False, *, diagnostic: str | None = None,
          messages: list[dict] | None = None, request_options: dict | None = None) -> dict:
    url, default_model = PROVIDERS[provider]
    model = os.getenv(f"{provider.upper()}_MODEL", default_model)
    payload = {"model": model, "messages": messages if messages is not None else [{"role": "user", "content": prompt}],
               "temperature": 0, "stream": streaming}
    if request_options:
        allowed = {"tools", "tool_choice", "response_format", "temperature", "top_p", "max_tokens"}
        if not request_options.keys() <= allowed:
            raise ValueError("Only capability fields and controlled sampling/output settings may be added to requests")
        for field, upper in (("temperature", 2), ("top_p", 1)):
            if field in request_options:
                value = request_options[field]
                if type(value) not in (int, float) or not 0 <= value <= upper:
                    raise ValueError(f"{field} must be a finite number between 0 and {upper}")
        if "max_tokens" in request_options:
            value = request_options["max_tokens"]
            if type(value) is not int or value <= 0:
                raise ValueError("max_tokens must be a positive integer")
        payload.update(request_options)
    if streaming:
        payload["stream_options"] = {"include_usage": True}
    if provider == "venice":
        payload["venice_parameters"] = {"include_venice_system_prompt": False}
    if diagnostic not in {None, "invalid_auth", "invalid_model", "invalid_parameter", "timeout",
                          "reasoning_medium", "reasoning_xhigh", "system_prompt_on"}:
        raise ValueError(f"Unknown diagnostic: {diagnostic}")
    if diagnostic in {"reasoning_medium", "reasoning_xhigh", "system_prompt_on"}:
        if provider != "venice":
            raise ValueError("These accounting diagnostics are Venice-only")
        if diagnostic == "system_prompt_on":
            payload["venice_parameters"]["include_venice_system_prompt"] = True
        else:
            payload["reasoning_effort"] = diagnostic.removeprefix("reasoning_")
    if diagnostic == "invalid_model":
        model = payload["model"] = "provider-eval-nonexistent-model"
    elif diagnostic == "invalid_parameter":
        payload["temperature"] = "provider-eval-invalid-number"
    elif diagnostic == "timeout":
        timeout = 0.001
    result = {
        "provider": provider, "model": MODEL, "provider_model_id": model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": {"url": url, "headers": {"Authorization": "Bearer <redacted>",
                    "Content-Type": "application/json"}, "json": payload},
        "response": None, "success": False, "error": None, "request_sent": False,
    }
    if diagnostic:
        result["diagnostic"] = {"case": diagnostic, "timeout_seconds": timeout, "exclude_from_benchmark": True}
    if provider == "ionet":
        result["request"]["headers"]["User-Agent"] = "provider-eval/0.1"
        result["request"]["headers"]["Accept"] = "text/event-stream" if streaming else "application/json"
    start = time.perf_counter()
    try:
        key = "provider-eval-invalid-key" if diagnostic == "invalid_auth" else os.getenv(f"{provider.upper()}_API_KEY")
        if not key:
            raise ValueError(f"Missing {provider.upper()}_API_KEY")
        headers = {**result["request"]["headers"], "Authorization": f"Bearer {key}"}
        request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers=headers, method="POST")
        start = time.perf_counter()
        result["request_sent"] = True
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            result["response"] = {"status_code": response.code, "headers": dict(response.headers), "body": None}
            if streaming and 200 <= response.code < 300:
                read_stream(response, result, start)
            else:
                body_text = response.read().decode("utf-8", errors="replace")
                result["response"]["body"] = body_text
                try:
                    result["response"]["body"] = json.loads(body_text)
                except json.JSONDecodeError:
                    result["error"] = {"type": "InvalidJSON", "message": "Response was not valid JSON; raw text retained."}
            body = result["response"]["body"]
            if isinstance(body, dict) and body.get("error"):
                result["error"] = {"type": "APIError", "message": json.dumps(body["error"])}
            if not 200 <= response.code < 300:
                result["error"] = {"type": "HTTPError", "message": f"HTTP {response.code}: {json.dumps(body)}"}
            result["success"] = 200 <= response.code < 300 and result["error"] is None
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    result["total_latency_seconds"] = time.perf_counter() - start
    return normalize(result)


def run(providers: list[str], prompt: str, timeout: float, output: Path, streaming: bool = False) -> list[dict]:
    output.mkdir(parents=True, exist_ok=False)
    results = []
    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        futures = [pool.submit(probe, provider, prompt, timeout, True) if streaming else pool.submit(probe, provider, prompt, timeout) for provider in providers]
        for future in as_completed(futures):
            result = future.result()
            (output / f"{result['provider']}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            results.append(result)
            status = "OK" if result["success"] else "FAILED"
            print(f"{result['provider']}: {status} ({result['total_latency_seconds']}s)")
    render_report(output)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", nargs="+", choices=PROVIDERS, default=list(PROVIDERS))
    parser.add_argument("--prompt", default="Reply with exactly: hello")
    parser.add_argument("--timeout", type=float, default=180, help="Network timeout in seconds (default: 180)")
    parser.add_argument("--stream", action="store_true", help="Measure streamed output and retain SSE events")
    parser.add_argument("--open", action="store_true", help="Open the completed HTML report in your browser")
    args = parser.parse_args()
    if not 0 < args.timeout < float("inf"):
        parser.error("--timeout must be a positive finite number")
    load_dotenv()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = ROOT / "results" / "raw" / run_id
    results = run(list(dict.fromkeys(args.providers)), args.prompt, args.timeout, output, args.stream)
    report = output / "report.html"
    print(f"Report: {report}")
    if args.open:
        webbrowser.open(report.as_uri())
    raise SystemExit(0 if all(result["success"] for result in results) else 1)


if __name__ == "__main__":
    main()
