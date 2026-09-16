"""Shared console output for the legacy single-provider request commands."""

import json

from manual_request import load_dotenv, probe
from provider_config import PROVIDER_LABELS


def main(provider: str) -> int:
    load_dotenv()
    prompt = f"Reply with exactly: hello from {PROVIDER_LABELS[provider]}"
    result = probe(provider, prompt, timeout=180)

    print("RAW REQUEST")
    print(json.dumps(result["request"], indent=2, ensure_ascii=False))
    print("\nRAW RESPONSE")
    print(json.dumps(result["response"], indent=2, ensure_ascii=False))

    if not result["success"]:
        print("\nERROR")
        print(json.dumps(result["error"], indent=2, ensure_ascii=False))
        return 1

    body = (result["response"] or {}).get("body")
    choices = body.get("choices") if isinstance(body, dict) else None
    choice = choices[0] if isinstance(choices, list) and choices else None
    message = choice.get("message") if isinstance(choice, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    print("\nPARSED RESULT")
    print(content if isinstance(content, str) else "No text content returned.")
    return 0
