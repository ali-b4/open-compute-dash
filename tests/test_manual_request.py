"""Offline checks for concurrency, failure capture, and safe report rendering."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import manual_request


class Response(io.BytesIO):
    code = 200
    headers = {"Content-Type": "application/json"}


class RequestTests(unittest.TestCase):
    @patch.dict(os.environ, {"VENICE_API_KEY": "test-secret"})
    def test_success_and_safe_html(self):
        with patch("urllib.request.urlopen", return_value=Response(b'{"text":"<script>alert(1)</script>"}')):
            result = manual_request.probe("venice", "hello", 1)
        self.assertTrue(result["success"])
        self.assertNotIn("test-secret", json.dumps(result))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "venice.json").write_text(json.dumps(result))
            report = manual_request.render_report(path).read_text()
            self.assertIn("&lt;script&gt;", report)
            self.assertNotIn("<script>", report)
            self.assertEqual(report.count("Not selected for this run"), 3)

    @patch.dict(os.environ, {"VENICE_API_KEY": "test-secret"})
    def test_http_error_with_non_json_body(self):
        error = urllib.error.HTTPError("https://example.com", 503, "Unavailable", {}, io.BytesIO(b"Unavailable"))
        with patch("urllib.request.urlopen", side_effect=error):
            result = manual_request.probe("venice", "hello", 1)
        self.assertFalse(result["success"])
        self.assertEqual(result["response"]["status_code"], 503)
        self.assertEqual(result["response"]["body"], "Unavailable")

    @patch.dict(os.environ, {"VENICE_API_KEY": "test-secret"})
    def test_timeout(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = manual_request.probe("venice", "hello", 1)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["type"], "TimeoutError")

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key(self):
        result = manual_request.probe("venice", "hello", 1)
        self.assertFalse(result["success"])
        self.assertIn("Missing VENICE_API_KEY", result["error"]["message"])

    def test_selected_providers_overlap_and_failure_does_not_stop_run(self):
        for selected in (["venice"], ["ionet"], ["venice", "ionet"], ["venice", "chutes"], list(manual_request.PROVIDERS)):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as directory:
                barrier = threading.Barrier(len(selected))
                def fake_probe(provider, prompt, timeout):
                    barrier.wait(timeout=3)
                    return {"provider": provider, "success": provider != "venice", "total_latency_seconds": 0,
                            "provider_model_id": "existing-model", "request": {}, "response": None, "error": None}
                output = Path(directory) / "run"
                with patch.object(manual_request, "probe", side_effect=fake_probe):
                    results = manual_request.run(selected, "hello", 1, output)
                self.assertEqual({r["provider"] for r in results}, set(selected))
                self.assertEqual(len(list(output.glob("*.json"))), len(selected))
                self.assertTrue((output / "report.html").exists())


if __name__ == "__main__":
    unittest.main()
