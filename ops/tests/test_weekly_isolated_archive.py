"""PR-14: synthetic-only immutable isolated weekly report migration tests."""
import base64
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from weekly_digest import digest, to_markdown
from weekly_isolated_archive import (
    REPO, BRANCH, PREFIX, ArchiveHold, GithubWeeklyStore,
    _git_blob_sha, _parse_unique, archive_report, validate_report,
)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/football-king-weekly.yml"
NOW = datetime(2026, 11, 6, 10, 22, tzinfo=timezone.utc)
DAY = "2026-11-06"


def report(at=NOW):
    body = to_markdown(digest(
        {"n": 0, "samples": [], "production_recommendations": "DISABLED"},
        {"as_of_utc": at.isoformat(), "quota": {"remaining": 150},
         "production_recommendations": "DISABLED"},
        at))
    return body.encode("utf-8")


class MemoryStore:
    def __init__(self):
        self.rows = {}
        self.writes = []
        self.verified = 0

    def verify_branch(self):
        self.verified += 1

    def get(self, path):
        if path not in self.rows:
            return None
        return self.rows[path], _git_blob_sha(self.rows[path])

    def put(self, path, raw):
        if path in self.rows:
            raise ArchiveHold("CONCURRENT_OR_EXISTING_WEEKLY_FILE")
        self.rows[path] = raw
        self.writes.append((path, raw))


class WeeklyIsolationTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()

    def publish(self, raw=None, *, day=DAY, now=NOW):
        return archive_report(report() if raw is None else raw,
                              day=day, store=self.store, now=now)

    def test_immutable_isolated_archive_reports_research_only(self):
        result = self.publish()
        self.assertEqual(result["status"], "RESEARCH_ONLY_ARCHIVED")
        self.assertEqual(result["reason"], "NEW_ISOLATED_WEEKLY_REPORT")
        self.assertEqual(result["archive_branch"], BRANCH)
        self.assertEqual(result["archive_path"], PREFIX + DAY + ".md")
        self.assertEqual(self.store.verified, 1)
        self.assertEqual(len(self.store.writes), 1)
        self.assertEqual(result["report_sha256"],
                         __import__("hashlib").sha256(report()).hexdigest())
        for key in ("source_independence_verified", "oos_improvement_verified",
                    "positive_ev_verified", "can_execute_bet"):
            self.assertIs(result[key], False)
        self.assertIs(result["legacy_main_report_unchanged"], True)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_new_file_must_read_back_exact_bytes_and_sha(self):
        class CountingStore(MemoryStore):
            def __init__(self):
                super().__init__()
                self.reads = 0

            def get(self, path):
                self.reads += 1
                return super().get(path)

        store = CountingStore()
        result = archive_report(report(), day=DAY, store=store, now=NOW)
        self.assertEqual(result["reason"], "NEW_ISOLATED_WEEKLY_REPORT")
        self.assertEqual(store.reads, 2, "A GitHub PUT response is not a verified readback")
        self.assertEqual(store.rows[PREFIX + DAY + ".md"], report())

    def test_created_file_without_verified_readback_is_hold(self):
        class BadReadbackStore(MemoryStore):
            def __init__(self, mode):
                super().__init__()
                self.mode = mode
                self.reads = 0

            def get(self, path):
                self.reads += 1
                if self.reads == 2:
                    if self.mode == "missing":
                        return None
                    if self.mode == "different":
                        corrupted = report() + b"\nTAMPERED\n"
                        return corrupted, _git_blob_sha(corrupted)
                    if self.mode == "wrong_sha":
                        return report(), "b" * 40
                    if self.mode == "http_403":
                        raise ArchiveHold("ARCHIVE_GITHUB_API_DENIED_OR_UNAVAILABLE")
                return super().get(path)

        for mode in ("missing", "different", "wrong_sha", "http_403"):
            with self.subTest(mode=mode):
                store = BadReadbackStore(mode)
                with self.assertRaises(ArchiveHold):
                    archive_report(report(), day=DAY, store=store, now=NOW)
                self.assertEqual(store.reads, 2)
                self.assertEqual(len(store.writes), 1)
                self.assertEqual(store.rows[PREFIX + DAY + ".md"], report())

    def test_duplicate_identical_week_report_is_idempotent(self):
        self.publish()
        result = self.publish()
        self.assertEqual(result["reason"], "EXISTING_IDENTICAL_WEEKLY_REPORT")
        self.assertEqual(len(self.store.writes), 1)

    def test_same_hk_day_different_body_is_conflict_not_overwrite(self):
        first = self.publish()
        altered = report(NOW + timedelta(minutes=1))
        with self.assertRaisesRegex(ArchiveHold, "SAME_WEEKLY_DATE_CONTENT_CONFLICT"):
            self.publish(altered, now=NOW + timedelta(minutes=2))
        self.assertEqual(self.store.rows[first["archive_path"]], report())
        self.assertEqual(len(self.store.writes), 1)

    def test_date_mismatch_rejected_before_branch_or_write(self):
        with self.assertRaisesRegex(ArchiveHold, "HK_WEEKLY_DATE_MISMATCH"):
            self.publish(day="2026-11-07")
        self.assertEqual(self.store.verified, 0)

    def test_invalid_path_and_day_input_rejected(self):
        for bad in ("main", "../2026-11-06", "2026-11-06\n", True):
            with self.subTest(day=bad):
                with self.assertRaisesRegex(ArchiveHold, "INVALID_WEEKLY_REPORT_DATE"):
                    self.publish(day=bad)

    def test_stale_or_future_report_rejected(self):
        for generated, now in (
            (NOW - timedelta(hours=25), NOW),
            (NOW + timedelta(minutes=7), NOW),
        ):
            with self.subTest(generated=generated):
                with self.assertRaisesRegex(ArchiveHold, "STALE_OR_FUTURE_WEEKLY_REPORT"):
                    self.publish(report(generated), now=now)
                self.assertEqual(self.store.verified, 0)

    def test_remove_mandatory_hold_or_research_disclaimer_rejected(self):
        for old, newer in (
            ("HOLD / DISABLED", "ENABLED"),
            ("只供研究，並非投注建議", "可即時投注"),
            ("## 六大聯賽上週樣本外研究", "## Winning picks"),
        ):
            with self.subTest(old=old):
                with self.assertRaisesRegex(ArchiveHold, "UNSAFE_OR_UNRECOGNIZED_WEEKLY_REPORT"):
                    self.publish(report().replace(old.encode("utf-8"), newer.encode("utf-8")))

    def test_extra_secret_and_raw_quote_fields_are_rejected(self):
        for token in ("TIPSME_API_KEY", "GH_TOKEN", "raw_quotes", "立即投注", "<script"):
            with self.subTest(token=token):
                blob = report() + ("\n" + token).encode("utf-8")
                with self.assertRaisesRegex(ArchiveHold, "UNSAFE_OR_UNRECOGNIZED_WEEKLY_REPORT"):
                    self.publish(blob)

    def test_invalid_utf8_and_control_character_rejected(self):
        with self.assertRaisesRegex(ArchiveHold, "INVALID_WEEKLY_REPORT_ENCODING"):
            self.publish(report() + b"\xff")
        with self.assertRaisesRegex(ArchiveHold, "UNSAFE_OR_UNRECOGNIZED_WEEKLY_REPORT"):
            self.publish(report() + b"\x00")

    def test_oversized_report_rejected(self):
        with self.assertRaisesRegex(ArchiveHold, "INVALID_WEEKLY_REPORT_SIZE"):
            self.publish(report() + b"a" * 30000)

    def test_unzoned_capture_time_rejected(self):
        blob = report().replace(NOW.isoformat().encode(), NOW.replace(tzinfo=None).isoformat().encode())
        with self.assertRaisesRegex(ArchiveHold, "UNZONED_WEEKLY_CAPTURE_TIME"):
            self.publish(blob)

    def test_no_implicit_live_data_or_betting_inputs(self):
        self.assertIn("市場Log Loss", report().decode())
        self.assertIn("尚未累積可以核對市場的完場樣本", report().decode())
        self.assertNotIn("可即時投注", report().decode())
        self.assertEqual(self.publish()["can_execute_bet"], False)


class GitHubStoreContractTests(unittest.TestCase):
    def test_git_blob_hash_matches_known_sample(self):
        data = b"abc"
        self.assertEqual(_git_blob_sha(data), "f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f")

    def test_missing_token_holds(self):
        with self.assertRaisesRegex(ArchiveHold, "ARCHIVE_GITHUB_TOKEN_UNAVAILABLE"):
            GithubWeeklyStore("")

    def test_ref_and_write_request_pinned_to_isolated_branch(self):
        store = GithubWeeklyStore("synthetic-token")
        observed = []
        class Response:
            def __init__(self, body):
                self.body = body
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, n=-1):
                return self.body
        def fake(req, timeout):
            observed.append((req, timeout))
            if req.get_method() == "PUT":
                body = json.loads(req.data)
                self.assertEqual(body["branch"], BRANCH)
                self.assertNotIn("sha", body)
                self.assertNotEqual(body["branch"], "main")
                return Response(json.dumps({"commit": {"sha": "a" * 40}}).encode())
            if "git/ref/heads/" in req.full_url:
                return Response(json.dumps({
                    "ref": "refs/heads/" + BRANCH,
                    "object": {"type": "commit", "sha": "a" * 40},
                }).encode())
            return Response(json.dumps({
                "type": "file", "path": PREFIX + DAY + ".md",
                "name": DAY + ".md",
                "sha": _git_blob_sha(report()), "size": len(report()),
                "content": base64.b64encode(report()).decode(),
                "encoding": "base64",
            }).encode())
        with patch("weekly_isolated_archive.GithubWeeklyStore._open", side_effect=fake):
            store.verify_branch()
            existing = store.get(PREFIX + DAY + ".md")
            store.put(PREFIX + DAY + ".md", report())
        self.assertEqual(existing[0], report())
        self.assertEqual([r[0].get_method() for r in observed], ["GET", "GET", "PUT"])
        self.assertIn("?ref=research%2Fweekly-report-archive", observed[1][0].full_url)
        self.assertTrue(observed[2][0].full_url.endswith("/contents/" + PREFIX + DAY + ".md"))

    def test_full_mock_github_put_then_fixed_ref_readback_and_replay(self):
        # Exercise the actual GitHub adapter, not just the in-memory store.
        # A real API is not called: every request is intercepted and checked.
        calls = []
        remote = {}

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, n=-1):
                return self.payload

        def fake_api(req, timeout):
            method = req.get_method()
            url = req.full_url
            calls.append((method, url))
            self.assertEqual(timeout, 12)
            if "/git/ref/heads/" in url:
                self.assertEqual(method, "GET")
                return Response(json.dumps({
                    "ref": "refs/heads/" + BRANCH,
                    "object": {"type": "commit", "sha": "a" * 40},
                }).encode())
            self.assertIn("/contents/" + PREFIX + DAY + ".md", url)
            if method == "GET":
                self.assertTrue(url.endswith("?ref=research%2Fweekly-report-archive"))
                if not remote:
                    raise HTTPError(url, 404, "not yet published", {}, None)
                data = remote["raw"]
                return Response(json.dumps({
                    "type": "file", "path": PREFIX + DAY + ".md",
                    "name": DAY + ".md", "sha": _git_blob_sha(data),
                    "size": len(data),
                    "content": base64.b64encode(data).decode("ascii"),
                    "encoding": "base64",
                }).encode())
            self.assertEqual(method, "PUT")
            self.assertEqual(url.split("?", 1)[0].split("/contents/", 1)[1],
                             PREFIX + DAY + ".md")
            payload = json.loads(req.data)
            self.assertEqual(payload["branch"], BRANCH)
            self.assertNotIn("sha", payload)
            self.assertNotIn("main", payload.values())
            self.assertNotIn("raw", remote)
            remote["raw"] = base64.b64decode(payload["content"])
            return Response(json.dumps({
                "commit": {"sha": "b" * 40}
            }).encode())

        store = GithubWeeklyStore("synthetic-token")
        with patch("weekly_isolated_archive.GithubWeeklyStore._open", side_effect=fake_api):
            created = archive_report(report(), day=DAY, store=store, now=NOW)
            duplicate = archive_report(report(), day=DAY, store=store, now=NOW)
        self.assertEqual(created["reason"], "NEW_ISOLATED_WEEKLY_REPORT")
        self.assertEqual(duplicate["reason"], "EXISTING_IDENTICAL_WEEKLY_REPORT")
        self.assertEqual(remote["raw"], report())
        self.assertEqual([m for m, _ in calls], [
            "GET", "GET", "PUT", "GET", "GET", "GET"])
        self.assertEqual(sum(m == "PUT" for m, _ in calls), 1)
        self.assertTrue(all("main" not in url for _, url in calls))

    def test_direct_write_to_main_and_path_traversal_rejected(self):
        store = GithubWeeklyStore("synthetic-token")
        with self.assertRaisesRegex(ArchiveHold, "UNAUTHORIZED_ARCHIVE_ENDPOINT"):
            store._api("PUT", "contents/reports/weekly/../../README.md",
                       data={"branch": "main", "content": "YWJj"})
        with self.assertRaisesRegex(ArchiveHold, "MAIN_OR_OVERWRITE_WRITE_FORBIDDEN"):
            store._api("PUT", "contents/" + PREFIX + DAY + ".md",
                       data={"branch": "main", "content": "YWJj"})
        with self.assertRaisesRegex(ArchiveHold, "MAIN_OR_OVERWRITE_WRITE_FORBIDDEN"):
            store._api("PUT", "contents/" + PREFIX + DAY + ".md",
                       data={"branch": BRANCH, "sha": "a"*40, "content": "YWJj"})
        with self.assertRaisesRegex(ArchiveHold, "UNEXPECTED_WEEKLY_FILE_PATH"):
            store.put("reports/weekly/../README.md", report())

    def test_github_archive_client_must_refuse_every_http_redirect(self):
        # A scoped URL allowlist only protects the initial request. Even a
        # GitHub-returned 301/302/307/308 must never forward GH_TOKEN or
        # the write payload to a second endpoint.
        from urllib.request import Request
        from weekly_isolated_archive import NoRedirect
        initial = Request("https://api.github.com/repos/CHANCHUNWA1989/football-king-report/contents/reports/weekly/2026-11-06.md")
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                self.assertIsNone(NoRedirect().redirect_request(
                    initial, None, status, "redirect", {},
                    "https://example.invalid/credential-collector"))

    def test_github_store_installs_redirect_deny_handler_for_get_and_put(self):
        from weekly_isolated_archive import NoRedirect
        with patch("weekly_isolated_archive.build_opener") as factory:
            GithubWeeklyStore("synthetic-token")
        self.assertEqual(factory.call_count, 1)
        self.assertTrue(any(isinstance(arg, NoRedirect)
                            for arg in factory.call_args.args))

    def test_api_403_and_create_conflict_are_hold(self):
        store = GithubWeeklyStore("synthetic-token")
        def forbidden(req, timeout):
            raise HTTPError(req.full_url, 403, "forbidden", {}, None)
        with patch("weekly_isolated_archive.GithubWeeklyStore._open", side_effect=forbidden):
            with self.assertRaisesRegex(ArchiveHold, "ARCHIVE_GITHUB_API_DENIED_OR_UNAVAILABLE"):
                store.verify_branch()
        def conflict(req, timeout):
            raise HTTPError(req.full_url, 409, "conflict", {}, None)
        with patch("weekly_isolated_archive.GithubWeeklyStore._open", side_effect=conflict):
            with self.assertRaisesRegex(ArchiveHold, "CONCURRENT_OR_EXISTING_WEEKLY_FILE"):
                store.put(PREFIX + DAY + ".md", report())

    def test_reject_corrupted_remote_blob_even_with_correct_filename(self):
        store = GithubWeeklyStore("synthetic-token")
        item = {
            "type": "file", "path": PREFIX + DAY + ".md", "name": DAY + ".md",
            "sha": "a" * 40, "encoding": "base64",
            "size": len(report()), "content": base64.b64encode(report()).decode(),
        }
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, n=-1):
                return json.dumps(item).encode()
        with patch("weekly_isolated_archive.GithubWeeklyStore._open", return_value=Response()):
            with self.assertRaisesRegex(ArchiveHold, "WEEKLY_BLOB_INTEGRITY_MISMATCH"):
                store.get(PREFIX + DAY + ".md")

    def test_duplicate_json_response_fields_rejected(self):
        with self.assertRaisesRegex(ArchiveHold, "DUPLICATE_GITHUB_RESPONSE_KEY"):
            _parse_unique('{"branch":"main","branch":"safe"}')

    def test_workflow_keeps_notification_but_never_uses_default_main_put(self):
        script = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python ops/weekly_isolated_archive.py", script)
        self.assertIn("gh issue create", script)
        self.assertIn("persist-credentials: false", script)
        self.assertIn("github.ref == 'refs/heads/main'", script)
        self.assertIn("python -m unittest discover -s ops/tests -q", script)
        self.assertNotIn("gh api -X PUT", script)
        self.assertNotIn('target="reports/weekly/', script)


if __name__ == "__main__":
    unittest.main()
