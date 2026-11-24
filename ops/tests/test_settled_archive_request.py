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


    def test_current_response_validates_blob_and_bytes(self):
        import hashlib
        script = ROOT / "ops/settled_archive_request.py"
        raw = b'{"samples":[]}\n'
        sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        response = {"type": "file", "path": "evidence/settled.json",
                    "encoding": "base64", "sha": sha, "size": len(raw),
                    "content": base64.b64encode(raw).decode()}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "response.json"
            target = Path(directory) / "current.json"
            def invoke(value):
                source.write_text(json.dumps(value))
                return subprocess.run([sys.executable, str(script),
                    "--current-response", str(source), "--output", str(target)],
                    capture_output=True, text=True)
            result = invoke(response)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), sha)
            self.assertEqual(target.read_bytes(), raw)
            target.unlink()
            for invalid in ({**response, "sha": "a"*40},
                            {**response, "content": "!!!"},
                            {**response, "size": len(raw)+1},
                            {**response, "path": "other.json"},
                            {**response, "encoding": "none"}):
                self.assertNotEqual(invoke(invalid).returncode, 0)
                self.assertFalse(target.exists())

    def _run_offline_archive_loop(self, fail_get=False):
        import os
        import shutil
        import textwrap
        bash = shutil.which("bash")
        if not bash or os.name != "posix":
            self.skipTest("offline Bash canary requires POSIX")
        workflow = WORKFLOW.read_text()
        block = workflow.split("          # Merge against the latest branch version", 1)[1]
        block = block.split("\n  notify_failure:", 1)[0]
        block = "set -euo pipefail\n" + textwrap.dedent(block[block.index("\n")+1:])
        sample = {
            "key": "old", "league": "epl",
            "kickoff_utc": "2026-10-10T12:00:00Z",
            "forecast_utc": "2026-10-10T11:00:00Z",
            "market_utc": "2026-10-10T10:00:00Z",
            "p": [.4,.3,.3], "m": [.3,.4,.3], "y": 1,
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED",
        }
        base = {"schema": "football-king-forward-research-1",
                "checked_utc": "2026-10-10T15:00:00Z", "n": 1,
                "results_independently_verified": False, "profitability_verified": False,
                "production_recommendations": "DISABLED"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"snapshot").mkdir()
            (root/"bin").mkdir()
            (root/"temp").mkdir()
            (root/"ops").symlink_to(ROOT/"ops", target_is_directory=True)
            (root/"state.json").write_text(json.dumps(
                {**base,"samples":[{**sample,"padding":"x"*150000}]}))
            (root/"snapshot/settled.json").write_text(json.dumps(
                {**base,"samples":[{**sample,"key":"incoming"}]}))
            fake = root/"bin/gh"
            fake.write_text("#!"+sys.executable+"\n"+textwrap.dedent(r'''
                import base64, hashlib, json, os, sys
                from pathlib import Path
                root = Path(os.environ["MOCK_ROOT"])
                state = root/"state.json"
                raw = state.read_bytes()
                sha = hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
                args = sys.argv[1:]
                if args[0] != "api" or "repos/mock/offline/contents/evidence/settled.json" not in args:
                    sys.exit(91)
                if "-X" not in args:
                    with (root/"events").open("a") as f:
                        f.write("GET\n")
                    if os.environ["MOCK_FAIL_GET"] == "1":
                        sys.exit(1)
                    print(json.dumps(dict(type="file",path="evidence/settled.json",
                        encoding="base64",sha=sha,size=len(raw),
                        content=base64.b64encode(raw).decode())))
                    sys.exit(0)
                with (root/"events").open("a") as f:
                    f.write("PUT\n")
                assert "--input" in args and max(map(len,args)) < 4096
                body = json.loads(Path(args[args.index("--input")+1]).read_text())
                assert body["sha"] == sha and body["branch"] == "main"
                assert len(body["content"]) > 131072
                incoming = json.loads(base64.b64decode(body["content"],validate=True))
                assert incoming["production_recommendations"] == "DISABLED"
                if not (root/"conflict").exists():
                    current = json.loads(raw)
                    row = dict(current["samples"][0],key="concurrent")
                    row.pop("padding",None)
                    current["samples"].append(row)
                    current["n"] += 1
                    state.write_text(json.dumps(current))
                    (root/"conflict").touch()
                    sys.exit(1)
                state.write_text(json.dumps(incoming))
                sys.exit(0)
            ''').lstrip())
            fake.chmod(0o700)
            sleep = root/"bin/sleep"
            sleep.write_text("#!/bin/sh\nexit 0\n")
            sleep.chmod(0o700)
            env = dict(os.environ, PATH=str(root/"bin")+os.pathsep+os.environ["PATH"],
                       MOCK_ROOT=str(root), MOCK_FAIL_GET=str(int(fail_get)),
                       RUNNER_TEMP=str(root/"temp"), GITHUB_REPOSITORY="mock/offline")
            result = subprocess.run([bash,"-c",block],cwd=root,env=env,
                                    capture_output=True,text=True,timeout=30)
            final = json.loads((root/"state.json").read_text())
            events = (root/"events").read_text().splitlines()
            return result, final, events

    def test_offline_conflict_retry_preserves_concurrent_record(self):
        result, final, events = self._run_offline_archive_loop()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ["GET","PUT","GET","PUT"])
        self.assertEqual(final["n"], 3)
        self.assertEqual({r["key"] for r in final["samples"]},
                         {"old","incoming","concurrent"})

    def test_offline_get_failure_never_attempts_put(self):
        result, final, events = self._run_offline_archive_loop(fail_get=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, ["GET"]*5)
        self.assertEqual(final["n"], 1)


if __name__ == "__main__":
    unittest.main()
