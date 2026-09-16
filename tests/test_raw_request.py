"""Legacy console commands share request handling without import-time calls."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch
import urllib.error

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import raw_request
from provider_config import PROVIDERS, PROVIDER_LABELS


class Response(io.BytesIO):
    code = 200
    headers = {"Content-Type": "application/json"}


class RawRequestTests(unittest.TestCase):
    providers = ("chutes", "venice", "darkbloom")

    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        dotenv = patch.object(raw_request, "load_dotenv")
        self.load_dotenv = dotenv.start()
        self.addCleanup(dotenv.stop)

    def run_command(self, provider):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as exit_status:
            runpy.run_path(str(SCRIPTS / f"{provider}_raw_request.py"), run_name="__main__")
        return exit_status.exception.code, output.getvalue()

    def test_imports_do_not_load_credentials_or_send_requests(self):
        with patch.object(raw_request, "probe") as probe, patch("urllib.request.urlopen") as send:
            for provider in self.providers:
                runpy.run_path(str(SCRIPTS / f"{provider}_raw_request.py"))
        self.load_dotenv.assert_not_called()
        probe.assert_not_called()
        send.assert_not_called()

    def test_commands_keep_prompts_and_redact_authorization(self):
        for provider in self.providers:
            with self.subTest(provider=provider):
                os.environ[f"{provider.upper()}_API_KEY"] = "test-secret"
                body = {"choices": [{"message": {"content": "hello"}}]}
                with patch("urllib.request.urlopen", return_value=Response(json.dumps(body).encode())) as send:
                    code, output = self.run_command(provider)
                request = send.call_args.args[0]
                payload = json.loads(request.data)
                self.assertEqual(request.full_url, PROVIDERS[provider][0])
                self.assertEqual(payload["model"], PROVIDERS[provider][1])
                self.assertEqual(payload["messages"], [{"role": "user", "content": f"Reply with exactly: hello from {PROVIDER_LABELS[provider]}"}])
                self.assertFalse(payload["stream"])
                self.assertEqual(payload["temperature"], 0)
                self.assertEqual(send.call_args.kwargs["timeout"], 180)
                if provider == "venice":
                    self.assertEqual(payload["venice_parameters"], {"include_venice_system_prompt": False})
                self.assertEqual(code, 0)
                self.assertIn("RAW REQUEST\n", output)
                self.assertIn("RAW RESPONSE\n", output)
                self.assertIn("PARSED RESULT\nhello\n", output)
                self.assertIn("Bearer <redacted>", output)
                self.assertNotIn("test-secret", output)
        self.assertEqual(self.load_dotenv.call_count, len(self.providers))

    def test_missing_keys_print_structured_errors_without_requests(self):
        with patch("urllib.request.urlopen") as send:
            for provider in self.providers:
                with self.subTest(provider=provider):
                    code, output = self.run_command(provider)
                    self.assertEqual(code, 1)
                    self.assertIn("RAW RESPONSE\nnull", output)
                    error = json.loads(output.split("\nERROR\n", 1)[1])
                    self.assertEqual(error["type"], "ValueError")
                    self.assertIn(f"Missing {provider.upper()}_API_KEY", error["message"])
        send.assert_not_called()

    def test_http_errors_preserve_non_json_body_and_exit_nonzero(self):
        for provider in self.providers:
            with self.subTest(provider=provider):
                os.environ[f"{provider.upper()}_API_KEY"] = "test-secret"
                error = urllib.error.HTTPError(PROVIDERS[provider][0], 503, "Unavailable", {}, io.BytesIO(b"Unavailable"))
                with patch("urllib.request.urlopen", side_effect=error):
                    code, output = self.run_command(provider)
                self.assertEqual(code, 1)
                self.assertIn('"status_code": 503', output)
                self.assertIn('"body": "Unavailable"', output)
                self.assertEqual(json.loads(output.split("\nERROR\n", 1)[1])["type"], "HTTPError")
                self.assertNotIn("test-secret", output)

    def test_success_without_text_does_not_crash(self):
        for body in ({}, {"choices": []}, {"choices": [None]}, {"choices": [{"message": None}]}, []):
            with self.subTest(body=body):
                # Exercise console formatting independently of response validation.
                result = {"success": True, "request": {}, "response": {"body": body}}
                with patch.object(raw_request, "probe", return_value=result):
                    code, output = self.run_command("chutes")
                self.assertEqual(code, 0)
                self.assertIn("PARSED RESULT\nNo text content returned.\n", output)


if __name__ == "__main__":
    unittest.main()
