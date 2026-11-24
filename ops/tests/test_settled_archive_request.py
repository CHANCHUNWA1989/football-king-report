"""Regression: large settlement payloads must not be passed through argv."""
import base64
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/football-king-iphone.yml"


class SettlementArchivePayloadTests(unittest.TestCase):
    def test_archive_uses_file_backed_request_not_large_argument(self):
        body = WORKFLOW.read_text(encoding="utf-8")
        block = body.split("# Merge against the latest branch version", 1)[1].split("\n  notify_failure:", 1)[0]
        self.assertNotIn('encoded="$(base64', block)
        self.assertNotIn('-f content="$encoded"', block)
        self.assertIn('--input "$RUNNER_TEMP/settled-request.json"', block)
        self.assertIn("python ops/settled_archive_request.py", block)

    def test_large_payload_roundtrip_and_small_argv(self):
        script = ROOT / "ops/settled_archive_request.py"
        raw = b'{"samples":[],"padding":"' + b"x" * 150000 + b'"}\n'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "merged.json"
            target = Path(directory) / "request.json"
            source.write_bytes(raw)
            for sha in ("a" * 40, ""):
                subprocess.run([sys.executable, str(script), "--merged", str(source),
                                "--sha", sha, "--output", str(target)], check=True)
                payload = json.loads(target.read_text())
                self.assertEqual(base64.b64decode(payload["content"], validate=True), raw)
                self.assertEqual(payload.get("sha"), sha or None)
                self.assertGreater(len(payload["content"]), 131072)
                self.assertEqual(payload["branch"], "main")
            target.unlink()
            result = subprocess.run([sys.executable, str(script), "--merged", str(source),
                                     "--sha", "invalid", "--output", str(target)],
                                    capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
