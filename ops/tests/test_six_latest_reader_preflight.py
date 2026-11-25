"""Synthetic-only tests for six latest source pointers' read contract."""

import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest

from ops.six_latest_reader_preflight import (
    LatestReadHold, SIX_LEAGUE_GROUP, STREAMS, inspect, main,
)


class SixLatestReaderPreflightTests(unittest.TestCase):
    NOW = "2026-11-23T16:00:00+00:00"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fk-latest-read-only-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.old = root / "old"
        self.new = root / "new"
        self.old.mkdir()
        self.new.mkdir()
        for filename, (schema, time_key, _, flags) in STREAMS.items():
            doc = {
                "schema": schema,
                "status": "HOLD",
                "production_recommendations": "DISABLED",
                time_key: "2026-11-23T12:00:00+00:00",
                **flags,
            }
            self.write(self.old, filename, doc)
            doc[time_key] = "2026-11-23T15:00:00+00:00"
            self.write(self.new, filename, doc)

    def write(self, root, filename, doc):
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, separators=(",", ":")))

    def doc(self, filename):
        return json.loads((self.new / filename).read_text())

    def test_all_six_contracts_parse_as_read_only_hold(self):
        receipt = inspect(self.old, self.new, self.NOW)
        self.assertEqual(receipt["snapshot_count"], 6)
        self.assertEqual(len(receipt["records"]), 6)
        self.assertTrue(receipt["six_league_timestamp_consistent"])
        self.assertFalse(receipt["tradable_market_freshness_verified"])
        self.assertFalse(receipt["historical_blob_retention_verified"])
        self.assertFalse(receipt["mobile_consumer_cutover_authorized"])
        self.assertEqual(receipt["production_recommendations"], "DISABLED")
        self.assertEqual({r["age_seconds"] for r in receipt["records"]}, {3600})

    def test_actual_byte_change_and_same_timestamp_are_distinguished(self):
        name = "sources/latest.json"
        doc = self.doc(name)
        doc["synthetic_payload_id"] = "new-but-same-clock"
        self.write(self.new, name, doc)
        out = inspect(self.old, self.new, self.NOW)
        match = next(r for r in out["records"] if r["path"] == name)
        self.assertFalse(match["byte_identical_to_baseline"])
        self.assertTrue(match["timestamp_nonregressing"])
        self.assertEqual(len(match["candidate_sha256"]), 64)

    def test_missing_required_pointer_fails_closed(self):
        (self.new / "sources/live_germany_latest.json").unlink()
        with self.assertRaisesRegex(LatestReadHold, "MISSING_OR_UNSAFE_LATEST_POINTER"):
            inspect(self.old, self.new, self.NOW)

    def test_mismatched_schema_rejected(self):
        name = "sources/latest.json"
        doc = self.doc(name)
        doc["schema"] = "unknown-future-schema"
        self.write(self.new, name, doc)
        with self.assertRaisesRegex(LatestReadHold, "LATEST_SCHEMA_OR_SAFETY_FLAG_MISMATCH"):
            inspect(self.old, self.new, self.NOW)

    def test_unapproved_safety_flag_rejected(self):
        name = "sources/seven_quality_gates_latest.json"
        doc = self.doc(name)
        doc["can_recommend_bets"] = True
        self.write(self.new, name, doc)
        with self.assertRaisesRegex(LatestReadHold, "UNAPPROVED_SOURCE_SAFETY_PROMOTION"):
            inspect(self.old, self.new, self.NOW)

    def test_second_source_status_disables_all_if_one_non_disabled(self):
        name = "sources/hkjc_tipsme_free_latest.json"
        doc = self.doc(name)
        doc["production_recommendations"] = "ENABLED"
        self.write(self.new, name, doc)
        with self.assertRaisesRegex(LatestReadHold, "LATEST_SCHEMA_OR_SAFETY_FLAG_MISMATCH"):
            inspect(self.old, self.new, self.NOW)

    def test_unknown_ready_like_status_is_not_compatible(self):
        name = "sources/six_league_free_latest.json"
        doc = self.doc(name)
        doc["status"] = "READY_FOR_PRODUCTION"
        self.write(self.new, name, doc)
        with self.assertRaisesRegex(LatestReadHold, "UNREVIEWED_LATEST_STATUS"):
            inspect(self.old, self.new, self.NOW)

    def test_six_league_triple_must_share_exact_utc_timestamp(self):
        name = SIX_LEAGUE_GROUP[1]
        doc = self.doc(name)
        doc["captured_utc"] = "2026-11-23T15:01:00+00:00"
        self.write(self.new, name, doc)
        with self.assertRaisesRegex(LatestReadHold, "SIX_LEAGUE_SNAPSHOT_SPLIT"):
            inspect(self.old, self.new, self.NOW)

    def test_candidate_timestamp_older_than_baseline_is_rejected(self):
        name = "sources/latest.json"
        doc = self.doc(name)
        doc["collected_utc"] = "2026-11-23T11:59:59+00:00"
        self.write(self.new, name, doc)
        with self.assertRaisesRegex(LatestReadHold, "LATEST_POINTER_CLOCK_ROLLBACK"):
            inspect(self.old, self.new, self.NOW)

    def test_future_timestamp_rejected(self):
        name = "sources/hkjc_tipsme_free_latest.json"
        doc = self.doc(name)
        doc["captured_utc"] = "2026-11-23T17:00:00+00:00"
        self.write(self.new, name, doc)
        with self.assertRaisesRegex(LatestReadHold, "LATEST_POINTER_FUTURE_TIMESTAMP"):
            inspect(self.old, self.new, self.NOW)

    def test_stale_germany_hourly_pointer_is_not_reported_usable(self):
        name = "sources/live_germany_latest.json"
        doc = self.doc(name)
        doc["collected_utc"] = "2026-11-23T10:00:00+00:00"
        self.write(self.new, name, doc)
        # Still forward relative to an older baseline.
        old = json.loads((self.old / name).read_text())
        old["collected_utc"] = "2026-11-23T09:00:00+00:00"
        self.write(self.old, name, old)
        with self.assertRaisesRegex(
                LatestReadHold, "LATEST_POINTER_OUTSIDE_RESEARCH_AGE_BUDGET"):
            inspect(self.old, self.new, self.NOW)

    def test_offset_naive_invalid_timezone_and_nans_are_rejected(self):
        name = "sources/latest.json"
        path = self.new / name
        original = path.read_bytes()
        for timestamp in ("2026-11-23T15:00:00", "2026-11-23T15:00:00+08:00",
                          "not-a-date", "2026-02-30T15:00:00Z"):
            with self.subTest(ts=timestamp):
                doc = self.doc(name) if path.read_bytes() == original else json.loads(original)
                doc["collected_utc"] = timestamp
                self.write(self.new, name, doc)
                with self.assertRaisesRegex(LatestReadHold, "INVALID_UTC_TIMESTAMP"):
                    inspect(self.old, self.new, self.NOW)
        path.write_bytes(original)
        doc = self.doc(name)
        path.write_text(json.dumps(doc)[:-1] + ',"x":NaN}')
        with self.assertRaisesRegex(LatestReadHold, "INVALID_LATEST_JSON"):
            inspect(self.old, self.new, self.NOW)

    def test_duplicate_json_keys_rejected_not_silently_last_wins(self):
        name = "sources/latest.json"
        doc = self.doc(name)
        path = self.new / name
        path.write_text(json.dumps(doc)[:-1] + ',"schema":"different"}')
        with self.assertRaisesRegex(LatestReadHold, "INVALID_LATEST_JSON"):
            inspect(self.old, self.new, self.NOW)

    def test_symlinked_document_and_directory_rejected(self):
        name = "sources/latest.json"
        p = self.new / name
        p.unlink()
        p.symlink_to(self.old / name)
        with self.assertRaisesRegex(LatestReadHold, "MISSING_OR_UNSAFE_LATEST_POINTER"):
            inspect(self.old, self.new, self.NOW)
        p.unlink()
        (self.new / "sources").rename(self.new / "sources-actual")
        (self.new / "sources").symlink_to(self.new / "sources-actual",
                                           target_is_directory=True)
        with self.assertRaises(LatestReadHold):
            inspect(self.old, self.new, self.NOW)

    def test_cli_always_returns_nonzero_even_with_six_valid_files(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([
                "--baseline-root", str(self.old),
                "--candidate-root", str(self.new),
                "--now-utc", self.NOW,
            ])
        self.assertEqual(rc, 1)
        result = json.loads(buf.getvalue())
        self.assertEqual(result["status"], "HOLD_SIX_LATEST_RESEARCH_READ_PREFLIGHT_ONLY")
        self.assertFalse(result["hosted_archive_write_authorized"])
        self.assertFalse(result["mobile_consumer_cutover_authorized"])

    def test_cli_failure_redacts_untrusted_values(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([
                "--baseline-root", str(self.old),
                "--candidate-root", str(self.new),
                "--now-utc", "do-not-echo-private-token",
            ])
        self.assertEqual(rc, 1)
        report = json.loads(buf.getvalue())
        self.assertEqual(report["status"], "HOLD_SIX_LATEST_PREFLIGHT_NOT_VERIFIABLE")
        self.assertNotIn("do-not-echo-private-token", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
