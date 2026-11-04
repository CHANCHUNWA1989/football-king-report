"""PR-13 read-only archive consumer: malicious GitHub response + stale tests."""
import base64
import copy
import hashlib
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hkjc_free_research import collect
from hkjc_isolated_archive import BRANCH, LATEST, ArchiveHold, _canonical
from hkjc_isolated_reader import (
    SCHEMA, _blob_sha1, hold, inspect_latest_record, read_isolated_latest,
    main,
)

NOW = datetime(2026, 11, 4, 8, 0, 0, tzinfo=timezone.utc)


def envelope(*, status_doc=None, data=None):
    doc = status_doc if status_doc is not None else collect(
        key="", now=NOW - timedelta(hours=1))
    raw = data if data is not None else _canonical(doc)
    return {
        "type": "file", "name": "latest.json", "path": LATEST,
        "encoding": "base64",
        "content": base64.b64encode(raw).decode("ascii"),
        "size": len(raw), "sha": _blob_sha1(raw),
    }


class FakeReply:
    def __init__(self, data):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, _=None):
        return self.data


def fake_get(record=None, *, code=None, exc=None, seen=None):
    def handle(request, timeout):
        if seen is not None:
            seen.append((request, timeout))
        if exc is not None:
            raise exc
        if code is not None:
            raise HTTPError(request.full_url, code, "failure", {}, None)
        return FakeReply(json.dumps(
            envelope() if record is None else record,
            separators=(",", ":"),
        ).encode("utf-8"))
    return handle


class ReadOnlyHkjcMetadataTests(unittest.TestCase):
    def test_recent_not_configured_is_still_hold(self):
        report = inspect_latest_record(envelope(), now=NOW)
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["status"], "HOLD")
        self.assertTrue(report["metadata_recent"])
        self.assertEqual(report["reason"], "NO_CONFIGURED_OR_QUALIFIED_THIRD_PARTY_MARKET")
        self.assertEqual(report["provider_status_at_capture"], "NOT_CONFIGURED")
        self.assertEqual(report["metadata_age_seconds"], 3600)
        for key in ("source_independent", "licensed_quote_redistribution",
                    "real_market_quote_verified", "source_clock_authenticated",
                    "model_scoring_eligible", "positive_ev_verified",
                    "can_execute_bet"):
            self.assertIs(report[key], False)
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_recent_research_only_never_becomes_market_eligible(self):
        doc = collect(key="", now=NOW - timedelta(minutes=40))
        doc["configured"] = True
        doc["status"] = "RESEARCH_ONLY"
        doc["reason"] = "FRESH_READ_ONLY_THIRD_PARTY_HKJC_RESEARCH"
        doc["requests_attempted"] = 3
        doc["hkjc_boards_checked"] = 1
        doc["fresh_had_events"] = 1
        doc["fresh_totals_events"] = 1
        record = envelope(status_doc=doc)
        result = inspect_latest_record(record, now=NOW)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "RECENT_ISOLATED_METADATA_ONLY_NO_MARKET_ADMISSION")
        self.assertEqual(result["provider_status_at_capture"], "RESEARCH_ONLY")
        self.assertEqual(result["market_coverage_at_capture"]["had"], 1)
        self.assertIs(result["real_market_quote_verified"], False)
        self.assertIs(result["positive_ev_verified"], False)

    def test_capture_older_than_daily_grace_is_hard_hold(self):
        doc = collect(key="", now=NOW - timedelta(hours=31))
        with self.assertRaisesRegex(ArchiveHold, "ARCHIVE_METADATA_STALE"):
            inspect_latest_record(envelope(status_doc=doc), now=NOW)

    def test_exact_30_hour_grace_accepted_only_as_metadata(self):
        doc = collect(key="", now=NOW - timedelta(hours=30))
        report = inspect_latest_record(envelope(status_doc=doc), now=NOW)
        self.assertTrue(report["metadata_recent"])
        self.assertEqual(report["status"], "HOLD")

    def test_future_timestamp_rejected(self):
        doc = collect(key="", now=NOW + timedelta(minutes=6))
        with self.assertRaisesRegex(ArchiveHold, "ARCHIVE_CAPTURE_IN_FUTURE"):
            inspect_latest_record(envelope(status_doc=doc), now=NOW)

    def test_wrong_identity_rejected_even_valid_sha(self):
        for field, bad in (
            ("path", "sources/hkjc_tipsme_free_latest.json"),
            ("path", "../main.json"),
            ("name", "main.json"), ("type", "symlink"),
            ("encoding", "utf-8"),
        ):
            with self.subTest(field=field):
                item = envelope()
                item[field] = bad
                with self.assertRaisesRegex(ArchiveHold, "LATEST_FILE_IDENTITY_MISMATCH"):
                    inspect_latest_record(item, now=NOW)

    def test_mismatched_blob_sha_size_and_bad_base64(self):
        for field, bad, error in (
            ("sha", "e" * 40, "LATEST_BLOB_INTEGRITY_MISMATCH"),
            ("size", 3, "LATEST_BLOB_INTEGRITY_MISMATCH"),
            ("content", "$$@", "LATEST_BASE64_INVALID"),
        ):
            with self.subTest(field=field):
                item = envelope()
                item[field] = bad
                with self.assertRaisesRegex(ArchiveHold, error):
                    inspect_latest_record(item, now=NOW)

    def test_wrong_provider_and_raw_quote_fields_fail_closed(self):
        for field, bad in (
            ("provider", "hkjc_official"),
            ("can_execute_bet", True),
            ("raw_quotes_published", True),
            ("production_recommendations", "ENABLED"),
        ):
            with self.subTest(field=field):
                doc = collect(key="", now=NOW)
                doc[field] = bad
                with self.assertRaisesRegex(ArchiveHold, "LATEST_UNSAFE_METADATA"):
                    inspect_latest_record(envelope(status_doc=doc), now=NOW)
        doc = collect(key="", now=NOW)
        doc["live_odds"] = [1.88, 1.91]
        with self.assertRaisesRegex(ArchiveHold, "LATEST_UNSAFE_METADATA"):
            inspect_latest_record(envelope(status_doc=doc), now=NOW)

    def test_json_duplicate_keys_fail_closed_even_with_matching_blob_sha(self):
        raw = b'{"schema":"safe","schema":"malicious"}\n'
        with self.assertRaisesRegex(ArchiveHold, "LATEST_UNSAFE_METADATA"):
            inspect_latest_record(envelope(data=raw), now=NOW)

    def test_noncanonical_whitespace_cannot_get_verified_as_writer_output(self):
        doc = collect(key="", now=NOW)
        raw = json.dumps(doc, ensure_ascii=False, sort_keys=True,
                         indent=2).encode("utf-8") + b"\n"
        with self.assertRaisesRegex(ArchiveHold, "NONCANONICAL_ARCHIVE_BYTES"):
            inspect_latest_record(envelope(data=raw), now=NOW)

    def test_invalid_nonfinite_data_fails(self):
        doc = collect(key="", now=NOW)
        # Inject non-finite JSON as untrusted GitHub bytes; the archive writer
        # would have rejected it before publication.
        raw = _canonical(doc).replace(b'"quota_remaining":null', b'"quota_remaining":NaN')
        with self.assertRaisesRegex(ArchiveHold, "LATEST_UNSAFE_METADATA"):
            inspect_latest_record(envelope(data=raw), now=NOW)

    def test_fixed_read_url_branch_and_get_only(self):
        seen = []
        r = read_isolated_latest(now=NOW, opener=fake_get(seen=seen))
        self.assertEqual(r["status"], "HOLD")
        self.assertTrue(r["metadata_recent"])
        self.assertEqual(len(seen), 1)
        req, timeout = seen[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(timeout, 12)
        self.assertIn("ref=research%2Fhkjc-free-metadata-archive", req.full_url)
        self.assertIn("/contents/" + LATEST, req.full_url)
        self.assertNotIn("hkjc_tipsme_free_latest.json", req.full_url)

    def test_missing_archive_does_not_fallback_to_main(self):
        seen = []
        r = read_isolated_latest(now=NOW, opener=fake_get(code=404, seen=seen))
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["reason"], "ISOLATED_LATEST_NOT_YET_ARCHIVED")
        self.assertEqual(len(seen), 1)

    def test_github_403_500_and_network_error_are_hold(self):
        for opener in (fake_get(code=403), fake_get(code=500),
                       fake_get(exc=URLError("offline"))):
            r = read_isolated_latest(now=NOW, opener=opener)
            self.assertEqual(r["status"], "HOLD")
            self.assertIs(r["metadata_recent"], False)
            self.assertIs(r["real_market_quote_verified"], False)

    def test_broken_json_and_truncated_http_response_fail(self):
        r = read_isolated_latest(now=NOW, opener=lambda *_args, **_kwargs: FakeReply(b"{"))
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["reason"], "INVALID_JSON")
        r = read_isolated_latest(
            now=NOW, opener=lambda *_args, **_kwargs: FakeReply(b" " * 32769))
        self.assertEqual(r["reason"], "GITHUB_METADATA_RESPONSE_SIZE_INVALID")

    def test_no_network_credential_needed_for_public_summary(self):
        seen = []
        r = read_isolated_latest(now=NOW, token=None, opener=fake_get(seen=seen))
        self.assertTrue(r["metadata_recent"])
        self.assertNotIn("Authorization", seen[0][0].headers)
        self.assertNotIn("TIPSME_API_KEY", str(r))

    def test_hold_factory_is_never_a_release_promotion(self):
        report = hold("UNSUPPORTED_PROVENANCE")
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["archive_branch"], BRANCH)
        self.assertFalse(report["metadata_recent"])
        self.assertFalse(report["can_execute_bet"])
        self.assertFalse(report["positive_ev_verified"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_main_cli_never_exits_zero_for_release(self):
        with patch("hkjc_isolated_reader.read_isolated_latest", return_value=hold("TEST")):
            with patch("sys.argv", ["hkjc_isolated_reader.py", "--no-auth"]):
                self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
