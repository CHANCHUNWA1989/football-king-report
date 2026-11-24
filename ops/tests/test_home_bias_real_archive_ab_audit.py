"""Synthetic adversarial tests for the genuine archive A/B analysis contract."""
import copy
from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from ops.home_bias_real_archive_ab_audit import (
    audit, compare_one, load_pinned_legacy_assess, read_archive,
)


NOW = datetime(2026, 11, 8, 3, tzinfo=timezone.utc)


def archived_rows():
    predictions = []
    for i in range(12):
        far = i < 10
        predictions.append({
            "event_id": "test-event-" + str(i), "league": "bundesliga",
            "home": f"Home_{i}", "away": f"Away_{i}",
            "kickoff_utc": (
                NOW + timedelta(days=9 if far else 2)).isoformat(),
            "prediction_utc": (NOW - timedelta(minutes=2)).isoformat(),
            "p_home": 0.68, "p_draw": 0.18, "p_away": 0.14,
            "score_ft": None, "status": "SCHEDULED",
            "production_recommendations": "DISABLED",
        })
    return {
        "status": "SHADOW_ONLY",
        "as_of_utc": (NOW - timedelta(minutes=2)).isoformat(),
        "predictions": predictions,
        "production_recommendations": "DISABLED",
    }


def legacy_func():
    # A/B tests replay the exact old source only where Git is available.
    return load_pinned_legacy_assess(Path(__file__).resolve().parents[2])


class ArchiveABTests(unittest.TestCase):
    def test_old_risk_bug_versus_repaired_false_quarantine(self):
        initial = archived_rows()
        preserved = copy.deepcopy(initial)
        report = compare_one(initial, NOW + timedelta(minutes=3), legacy_func())
        self.assertEqual(initial, preserved)
        self.assertEqual(report["legacy_model_only_count"], 0)
        self.assertEqual(report["fixed_model_only_count"], 2)
        self.assertEqual(report["delta_fixed_minus_legacy_model_only"], 2)
        bundesliga = report["by_league"]["bundesliga"]
        self.assertEqual(bundesliga["legacy_eligible_pre_match_claims"], 12)
        self.assertEqual(bundesliga["fixed_time_valid_eligible"], 2)
        self.assertTrue(bundesliga["legacy_quarantine_flag"])
        self.assertFalse(bundesliga["fixed_quarantine_flag"])

    def test_exact_archived_source_roundtrip_untouched(self):
        source = archived_rows()
        body = json.dumps(source, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "shadow" / "trial.json.gz"
            archive.parent.mkdir()
            archive.write_bytes(gzip.compress(body))
            before = archive.read_bytes()
            record, now, meta = read_archive("shadow/trial.json.gz", repo_root=root)
            self.assertEqual(record, source)
            self.assertEqual(archive.read_bytes(), before)
            self.assertEqual(meta["input_record_count"], 12)
            self.assertEqual(meta["archived_as_of_utc"], source["as_of_utc"])
            result = audit(["shadow/trial.json.gz"],
                           repo_root=root, legacy=legacy_func())
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["snapshots_checked"], 1)
            self.assertEqual(result["results"][0]["fixed_model_only_count"], 2)
            self.assertFalse(result["positive_ev_verified"])
            self.assertFalse(result["model_promoted"])
            self.assertEqual(result["certified_prospective_samples"], 0)

    def test_missing_or_duplicate_archives_fail_closed_no_partial_metric(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "shadow" / "trial.json.gz"
            path.parent.mkdir()
            path.write_bytes(gzip.compress(json.dumps(archived_rows()).encode()))
            result = audit(["shadow/trial.json.gz", "shadow/trial.json.gz"],
                           repo_root=root, legacy=legacy_func())
            self.assertEqual(result["reason"], "REAL_ARCHIVED_AB_BLOCKED")
            self.assertNotIn("results", result)
            self.assertEqual(result["completed_before_first_block"], 1)
            invalid = audit(["../shadow/trial.json.gz"],repo_root=root,
                            legacy=legacy_func())
            self.assertEqual(invalid["reason"], "REAL_ARCHIVED_AB_BLOCKED")
            self.assertNotIn("results", invalid)

    def test_duplicate_json_key_and_wrong_status_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "shadow" / "trial.json.gz"
            path.parent.mkdir()
            raw = json.dumps(archived_rows()).replace(
                '"status": "SHADOW_ONLY"',
                '"status": "SHADOW_ONLY", "status": "ENABLED"', 1)
            path.write_bytes(gzip.compress(raw.encode()))
            with self.assertRaises(ValueError):
                read_archive("shadow/trial.json.gz",repo_root=root)
            data = archived_rows()
            data["production_recommendations"]="ENABLED"
            path.write_bytes(gzip.compress(json.dumps(data).encode()))
            with self.assertRaises(ValueError):
                read_archive("shadow/trial.json.gz",repo_root=root)

    def test_bounded_decompress_and_archive_original_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "shadow" / "too_big.json.gz"
            path.parent.mkdir()
            path.write_bytes(gzip.compress(b"a" * 3_000_100))
            with self.assertRaises(ValueError):
                read_archive("shadow/too_big.json.gz",repo_root=root)
            path.write_bytes(gzip.compress(json.dumps(archived_rows()).encode())
                             + b"extra")
            with self.assertRaises(ValueError):
                read_archive("shadow/too_big.json.gz",repo_root=root)


if __name__ == "__main__":
    unittest.main()
