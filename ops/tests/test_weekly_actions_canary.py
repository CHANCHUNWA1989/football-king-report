"""Fail-first offline tests for read-only GitHub Actions archive canary."""
import base64
import json
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from weekly_actions_canary import (
    ARCHIVE_BRANCH, CANARY_PATH, EXPECTED_BLOB_SHA, EXPECTED_PAYLOAD,
    ArchiveCanaryHold, probe,
)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/weekly-archive-actions-readback-canary.yml"
BASE = "https://api.github.com/repos/CHANCHUNWA1989/football-king-report/"
EXPECTED_RAW = (json.dumps(EXPECTED_PAYLOAD, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


class Reply:
    def __init__(self, value):
        self.data = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, max_size=-1):
        return self.data


class FakeGitHub:
    def __init__(self, *, altered=False, bad_sha=False, main_present=False,
                 wrong_ref=False, forbidden=False):
        self.calls = []
        self.altered = altered
        self.bad_sha = bad_sha
        self.main_present = main_present
        self.wrong_ref = wrong_ref
        self.forbidden = forbidden

    def open(self, req, timeout=0):
        url = req.full_url
        self.calls.append((req.get_method(), url, timeout))
        if self.forbidden:
            raise HTTPError(url, 403, "Permission denied", {}, None)
        if "/git/ref/heads/" in url:
            return Reply({
                "ref": "refs/heads/" + ("main" if self.wrong_ref else ARCHIVE_BRANCH),
                "object": {"type": "commit", "sha": "a" * 40},
            })
        if "?ref=main" in url:
            if not self.main_present:
                raise HTTPError(url, 404, "Not found", {}, None)
            return Reply(self.file_response())
        return Reply(self.file_response())

    def file_response(self):
        data = EXPECTED_RAW + b"\nTAMPER" if self.altered else EXPECTED_RAW
        return {
            "type": "file", "path": CANARY_PATH,
            "name": CANARY_PATH.rsplit("/", 1)[1],
            "encoding": "base64", "size": len(data),
            "sha": "f" * 40 if self.bad_sha else EXPECTED_BLOB_SHA,
            "content": base64.b64encode(data).decode("ascii"),
        }


class ActionCanaryTests(unittest.TestCase):
    def test_authenticated_readonly_canary_holds_no_betting_claim(self):
        api = FakeGitHub()
        result = probe(token="synthetic-ci-token", opener=api)
        self.assertEqual(result["status"], "READ_ONLY_CANARY_VERIFIED")
        self.assertEqual(result["archive_branch"], ARCHIVE_BRANCH)
        self.assertFalse(result["write_token_verified"])
        self.assertFalse(result["issue_notification_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual([method for method, _, _ in api.calls],
                         ["GET", "GET", "GET"])
        self.assertTrue(all(t == 12 for _, _, t in api.calls))
        self.assertTrue(api.calls[1][1].endswith(
            "?ref=research%2Fweekly-report-archive"))
        self.assertTrue(api.calls[2][1].endswith("?ref=main"))

    def test_corrupted_or_changed_file_fails_closed(self):
        for overrides in ({"altered": True}, {"bad_sha": True},
                          {"main_present": True}, {"wrong_ref": True},
                          {"forbidden": True}):
            with self.subTest(overrides=overrides), self.assertRaises(ArchiveCanaryHold):
                probe(token="synthetic-ci-token", opener=FakeGitHub(**overrides))

    def test_token_missing_fails_closed(self):
        for tok in ("", None, "   "):
            with self.subTest(tok=tok), self.assertRaises(ArchiveCanaryHold):
                probe(token=tok, opener=FakeGitHub())

    def test_canary_workflow_is_read_only_and_no_providers_or_notifications(self):
        code = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("contents: read", code)
        self.assertNotIn("contents: write", code)
        self.assertNotIn("issues: write", code)
        self.assertNotIn("pull_request_target", code)
        self.assertNotIn("workflow_run:", code)
        self.assertNotIn("gh issue create", code)
        self.assertNotIn("THE_ODDS_API_KEY", code)
        self.assertNotIn("git push", code)
        self.assertIn("python ops/weekly_actions_canary.py", code)
        self.assertIn("persist-credentials: false", code)
        self.assertIn("research/vnext-pr14-isolated-weekly-report-20261104", code)


if __name__ == "__main__":
    unittest.main()
