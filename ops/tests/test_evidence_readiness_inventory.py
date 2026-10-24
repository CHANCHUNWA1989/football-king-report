import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_readiness_inventory import inventory

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def fixtures(stamp="2026-10-15T10:00:00Z"):
    market = {"as_of_utc": stamp, "event_count": 110,
              "leagues": [{"league": "epl"}, {"league": "bundesliga"}]}
    summary = {"captured_utc": stamp, "evidence_progress": {
        "settled_cases_in_archive": 28, "settled_cases_required": 300,
        "independently_verified_result_cases": 0}}
    gates = {"captured_utc": stamp, "passed": 1, "total": 7, "checks": [
        {"key": "model_promotion_safety", "state": "PASS"}]}
    return market, summary, gates


class ReadinessTests(unittest.TestCase):
    def test_reported_aggregate_cannot_hide_missing_or_duplicate_checks(self):
        for checks in ([], [{"state": "PASS"}] * 7,
                       [{"key": "model_promotion_safety", "state": "PASS"},
                        {"key": "model_promotion_safety", "state": "HOLD"}]):
            with self.subTest(checks=checks):
                market, summary, gates = fixtures()
                gates.update(passed=7, total=7, checks=checks)
                result = inventory(market, summary, gates, now=NOW)
                self.assertEqual(result["quality_gates_passed"], 0)
                self.assertEqual(result["quality_gates_total"], 7)
                self.assertIn("QUALITY_GATES_INCOMPLETE", result["blockers"])

    def test_true_gap_is_independently_verified_not_archived_candidates(self):
        result = inventory(*fixtures(), now=NOW)
        self.assertEqual(result["remaining_independent_settlements"], 300)
        self.assertEqual(result["settled_archive_candidates"], 28)
        self.assertEqual(result["quality_gates_passed"], 1)
        self.assertFalse(result["ready_for_production"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_stale_snapshot_is_hold(self):
        result = inventory(*fixtures("2026-10-13T10:00:00Z"), now=NOW)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("STALE_OR_INVALID_SNAPSHOTS", result["blockers"])

    def test_future_snapshot_is_hold(self):
        result = inventory(*fixtures("2026-10-16T10:00:00Z"), now=NOW)
        self.assertEqual(result["status"], "HOLD")

    def test_invalid_independent_count_is_rejected(self):
        market, summary, gates = fixtures()
        summary["evidence_progress"]["independently_verified_result_cases"] = 29
        with self.assertRaises(ValueError):
            inventory(market, summary, gates, now=NOW)


if __name__ == "__main__":
    unittest.main()
