"""PR-12 isolated HKJC metadata archive tests: no real provider requests or bets."""
import copy
import hashlib
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hkjc_free_research import collect
from hkjc_isolated_archive import (
    ALLOWED_FIELDS, BRANCH, ROOT, LATEST, ArchiveHold, GitHubArchiveStore,
    _parse_unique, archive,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT_DIR / ".github/workflows/football-king-hkjc-free-research.yml"
FIXED = datetime(2026, 11, 4, 8, 0, 0, tzinfo=timezone.utc)


def doc(at=FIXED):
    return collect(key="", now=at)


class FakeStore:
    def __init__(self):
        self.files = {}
        self.writes = []
        self.verification_count = 0
        self.conflicts = 0

    def verify_branch(self):
        self.verification_count += 1

    def get(self, name):
        row = self.files.get(name)
        if row is None:
            return None
        raw, sha = row
        return raw, sha

    def put(self, name, raw, *, sha=None):
        if self.conflicts:
            self.conflicts -= 1
            raise ArchiveHold("CONCURRENT_WRITE_CONFLICT")
        prior = self.files.get(name)
        if prior is None and sha is not None:
            raise ArchiveHold("CONCURRENT_WRITE_CONFLICT")
        if prior is not None and sha != prior[1]:
            raise ArchiveHold("CONCURRENT_WRITE_CONFLICT")
        version = hashlib.sha1(raw + str(len(self.writes)).encode()).hexdigest()
        self.files[name] = (raw, version)
        self.writes.append((name, raw, sha))


class BranchArchiveTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()

    def publish(self, document=None, *, run=12345, attempt=1, now=None):
        return archive(
            doc() if document is None else document,
            run_id=run, attempt=attempt,
            store=self.store, now=now if now is not None else FIXED + timedelta(minutes=2),
        )

    def test_only_two_fixed_branch_history_and_latest_writes(self):
        out = self.publish()
        self.assertEqual(out["status"], "RESEARCH_ARCHIVED_ISOLATED")
        self.assertEqual(out["archive_branch"], BRANCH)
        self.assertEqual(out["latest_result"], "LATEST_UPDATED")
        self.assertEqual(self.store.verification_count, 1)
        self.assertEqual(len(self.store.writes), 2)
        self.assertEqual(self.store.writes[1][0], LATEST)
        self.assertTrue(self.store.writes[0][0].startswith(ROOT + "/history/2026/11/04/"))
        self.assertNotIn("/main", out["history_path"])
        self.assertEqual(hashlib.sha256(self.store.writes[0][1]).hexdigest(),
                         out["history_sha256"])
        self.assertFalse(out["real_source_rights_verified"])
        self.assertFalse(out["independent_market_verified"])
        self.assertFalse(out["can_execute_bet"])
        self.assertFalse(out["positive_ev_verified"])
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_same_run_is_idempotent(self):
        first = self.publish()
        second = self.publish()
        self.assertEqual(first["history_path"], second["history_path"])
        self.assertEqual(second["latest_result"], "IDENTICAL_LATEST_PRESERVED")
        self.assertEqual(len(self.store.writes), 2)

    def test_multiple_runs_preserve_old_history(self):
        first = self.publish()
        next_doc = doc(FIXED + timedelta(minutes=4))
        newer = self.publish(next_doc, run=12346, now=FIXED + timedelta(minutes=6))
        self.assertNotEqual(first["history_path"], newer["history_path"])
        self.assertEqual(newer["latest_result"], "LATEST_UPDATED")
        self.assertEqual(len(self.store.writes), 4)
        self.assertIn(first["history_path"], self.store.files)
        self.assertIn(newer["history_path"], self.store.files)

    def test_late_older_capture_cannot_overwrite_newer_latest(self):
        future = doc(FIXED + timedelta(minutes=3))
        self.publish(future, run=12346, now=FIXED + timedelta(minutes=5))
        old = self.publish(doc(), run=12345, now=FIXED + timedelta(minutes=6))
        self.assertEqual(old["latest_result"], "NEWER_LATEST_PRESERVED")
        self.assertEqual(len(self.store.writes), 3)

    def test_conflicting_same_timestamp_does_not_overwrite_latest(self):
        self.publish()
        other = doc()
        other["reason"] = "SCHEDULE_LOOKUP_FAILED"
        with self.assertRaisesRegex(ArchiveHold, "SAME_CAPTURE_DIFFERENT_METADATA"):
            self.publish(other, run=12346)
        self.assertEqual(len(self.store.writes), 3)

    def test_conflicting_replay_run_and_attempt_rejected(self):
        self.publish()
        fake = doc()
        fake["reason"] = "SCHEDULE_LOOKUP_FAILED"
        with self.assertRaisesRegex(ArchiveHold, "HISTORICAL_RUN_IDENTITY_CONFLICT"):
            self.publish(fake)
        self.assertEqual(len(self.store.writes), 2)

    def test_single_cas_conflict_is_retried_and_still_safe(self):
        self.publish()
        self.store.conflicts = 1
        newer = doc(FIXED + timedelta(minutes=4))
        out = self.publish(newer, run=12346, now=FIXED + timedelta(minutes=6))
        self.assertEqual(out["latest_result"], "LATEST_UPDATED")

    def test_unresolved_cas_conflict_fails_not_silently_successful(self):
        self.publish()
        new_doc = doc(FIXED + timedelta(minutes=4))
        # A crash or conflict in archived history is fail-closed before latest.
        self.store.conflicts = 10
        with self.assertRaisesRegex(ArchiveHold, "CONCURRENT_WRITE_CONFLICT"):
            self.publish(new_doc, run=12346, now=FIXED + timedelta(minutes=6))

    def test_unknown_quote_or_secret_key_cannot_be_published(self):
        for key, value in (("raw_quote", {"over": 1.82}),
                           ("API_KEY", "example-secret"),
                           ("market_executable_verified", True),
                           ("license_override", True)):
            with self.subTest(key=key):
                x = doc()
                x[key] = value
                with self.assertRaisesRegex(ArchiveHold, "UNRECOGNIZED_OR_MISSING"):
                    self.publish(x)
                self.assertEqual(len(self.store.writes), 0)

    def test_readonly_or_wagering_claims_refused(self):
        for key, value in (("raw_quotes_published", True),
                           ("bookmaker_names_published", True),
                           ("production_recommendations", "ENABLED"),
                           ("can_execute_bet", True),
                           ("external_license_redistribution_verified", True)):
            with self.subTest(key=key):
                x = doc()
                x[key] = value
                with self.assertRaisesRegex(ArchiveHold, "UNSAFE_HKJC_METADATA"):
                    self.publish(x)

    def test_source_document_location_and_reason_must_match(self):
        for key, value in (("source", "https://example.invalid/scrape"),
                           ("reason", "sensitive-token-was-logged")):
            with self.subTest(key=key):
                x = doc()
                x[key] = value
                with self.assertRaisesRegex(ArchiveHold, "UNVERIFIED_METADATA_OR_SOURCE"):
                    self.publish(x)

    def test_stale_and_future_capture_rejected_before_branch_check(self):
        for when in (FIXED + timedelta(days=2),
                     FIXED - timedelta(minutes=7)):
            with self.subTest(when=str(when)):
                with self.assertRaisesRegex(ArchiveHold, "STALE_OR_FUTURE_ARCHIVE"):
                    self.publish(now=when)
                self.assertEqual(self.store.verification_count, 0)

    def test_wrong_run_identifiers_and_bool_rejected(self):
        for rid, attempt in ((0, 1), (True, 1), (10**15, 1),
                             (1, False), (1, -1), ("12345", 1)):
            with self.subTest(rid=rid, attempt=attempt):
                with self.assertRaises(ArchiveHold):
                    self.publish(run=rid, attempt=attempt)

    def test_duplicate_json_and_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(ArchiveHold, "DUPLICATE_JSON_KEY"):
            _parse_unique('{"status":"HOLD","status":"RESEARCH_ONLY"}')
        with self.assertRaisesRegex(ArchiveHold, "NONFINITE_JSON"):
            _parse_unique('{"bad":NaN}')

    def test_previous_latest_corrupted_never_replaced(self):
        self.publish()
        self.store.files[LATEST] = (b'{"status":"ENABLED"}', "e" * 40)
        newer = doc(FIXED + timedelta(minutes=4))
        with self.assertRaisesRegex(ArchiveHold, "PREVIOUS_METADATA_CORRUPT"):
            self.publish(newer, run=12346, now=FIXED + timedelta(minutes=6))

    def test_all_report_fields_are_strictly_allowlisted(self):
        self.assertEqual(set(doc()), ALLOWED_FIELDS)


class GitHubApiIsolationTests(unittest.TestCase):
    def test_each_contents_write_pins_archive_branch_not_main(self):
        store = GitHubArchiveStore("synthetic-test-token")
        requests = []
        class Response:
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self, n=-1):
                return self.payload
        def handler(req, timeout):
            requests.append(req)
            if req.get_method() == "PUT":
                body = json.loads(req.data)
                self.assertEqual(body["branch"], BRANCH)
                self.assertNotEqual(body["branch"], "main")
                return Response(json.dumps({"commit": {"sha": "a" * 40}}).encode())
            return Response(json.dumps({
                "ref": "refs/heads/" + BRANCH,
                "object": {"type": "commit", "sha": "a" * 40},
            }).encode())
        with patch("hkjc_isolated_archive.urlopen", side_effect=handler):
            store.verify_branch()
            store.put(LATEST, b'{"safe":true}\n', sha=None)
        self.assertEqual(requests[1].get_method(), "PUT")
        self.assertTrue(requests[1].full_url.endswith("/contents/" + LATEST))
        self.assertTrue(requests[0].full_url.endswith("/git/ref/heads/" + BRANCH))

    def test_api_permissions_error_is_hold(self):
        store = GitHubArchiveStore("synthetic-test-token")
        def deny(*a, **kw):
            raise HTTPError("https://api.github.com", 403, "forbidden", {}, None)
        with patch("hkjc_isolated_archive.urlopen", side_effect=deny):
            with self.assertRaisesRegex(ArchiveHold, "GITHUB_ARCHIVE_API_UNAVAILABLE"):
                store.verify_branch()

    def test_prevent_general_github_content_api_write(self):
        store = GitHubArchiveStore("synthetic-test-token")
        with self.assertRaisesRegex(ArchiveHold, "UNAUTHORIZED_GITHUB_ARCHIVE_PATH"):
            store._request("PUT", "contents/sources/hkjc_tipsme_free_latest.json",
                           payload={"branch": "main", "content": "YWJj"})
        with self.assertRaisesRegex(ArchiveHold, "UNAUTHORIZED_GITHUB_ARCHIVE_WRITE"):
            store._request("PUT", "contents/" + LATEST,
                           payload={"branch": "main", "content": "YWJj"})

    def test_workflow_preserves_collect_artifact_and_never_publishes_main(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: football-king-hkjc-tipsme-free-metadata", content)
        self.assertIn("python ops/hkjc_isolated_archive.py", content)
        self.assertIn("test_hkjc_isolated_archive.py", content)
        self.assertIn("persist-credentials: false", content)
        self.assertIn("github.ref == 'refs/heads/main'", content)
        self.assertNotIn('gh api -X PUT "repos/$GITHUB_REPOSITORY/contents/', content)
        self.assertNotIn('sources/hkjc_tipsme_free_latest.json', content)
        self.assertNotIn("git push", content)


if __name__ == "__main__":
    unittest.main()
