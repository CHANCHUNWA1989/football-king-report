"""Synthetic regression tests for descriptive readiness identity accounting."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recommendation_readiness import grounded_progress


def row(stamp="2026-11-01T23:30:00Z", **changes):
    return dict({
        "league": "epl",
        "key": json.dumps(["epl", "team-a", "team-b", stamp]),
        "kickoff_utc": stamp,
        "y": 1,
        "fixture_result_source_independently_verified": False,
    }, **changes)


def audit(rows):
    return grounded_progress({"samples": rows}, {}, {}, {})


class CanonicalReadinessTests(unittest.TestCase):
    def test_equivalent_offsets_are_one_fixture_and_one_utc_week(self):
        a = row()
        b = row("2026-11-02T07:30:00+08:00")
        for records in ([a, b], [b, a]):
            result = audit(records)
            self.assertEqual(result["settled_cases_in_archive"], 1)
            self.assertEqual(result["independent_week_blocks"], 1)
            self.assertEqual(result["independently_verified_result_cases"], 0)

    def test_conflicting_duplicates_are_quarantined_in_both_orders(self):
        a, b = row(), row("2026-11-02T07:30:00+08:00", y=2)
        for records in ([a, b], [b, a], [a, b, a]):
            result = audit(records)
            self.assertEqual(result["settled_cases_in_archive"], 0)
            self.assertEqual(result["conflicting_fixture_keys"], 1)

    def test_invalid_identity_and_unhashable_fields_are_rejected(self):
        invalid = [row(key=[]), row(league=[]), row(key="not json"),
                   row(league="seriea"), row(key=json.dumps(["epl", "a", "a", "2026-11-01T23:30:00Z"])),
                   row(kickoff_utc="2026-11-01T22:30:00Z"),
                   row(kickoff_utc="2026-11-01T23:30:00")]
        result = audit(invalid)
        self.assertEqual(result["settled_cases_in_archive"], 0)
        self.assertEqual(result["invalid_fixture_rows"], len(invalid))
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_oversized_batch_not_partially_counted(self):
        result = audit([row()] * 20001)
        self.assertEqual(result["settled_cases_in_archive"], 0)
        self.assertFalse(result["archive_identity_scan_complete"])

    def test_marked_claim_not_certification(self):
        result = audit([row(fixture_result_source_independently_verified=True)])
        self.assertEqual(result["result_rows_marked_independently_verified"], 1)
        self.assertEqual(result["independently_verified_result_cases"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
