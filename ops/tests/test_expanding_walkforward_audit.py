"""Synthetic regression cases for expanding walk-forward research audit."""
import copy
import unittest
from datetime import datetime, timedelta, timezone

from ops.expanding_walkforward_audit import walk_forward


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def fixtures(count=12):
    rows = []
    for i in range(count):
        kickoff = BASE + timedelta(days=i + 1)
        rows.append({
            "event_id": f"synthetic-{i}",
            "forecast_at": (kickoff - timedelta(hours=2)).isoformat(),
            "kickoff_at": kickoff.isoformat(),
            "settled_at": (kickoff + timedelta(hours=3)).isoformat(),
            "probabilities": {"H": .5, "D": .3, "A": .2},
            "outcome": ("H", "D", "A")[i % 3],
        })
    return rows


class ExpandingWalkForwardTests(unittest.TestCase):
    def test_all_test_matches_counted_and_multiple_folds(self):
        report = walk_forward(fixtures(), min_train=4, test_size=3)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["fold_count"], 3)
        self.assertEqual([f["test_count"] for f in report["folds"]], [3, 3, 2])
        self.assertEqual(report["evaluated_count"], 8)
        self.assertEqual(report["reason"], "INDEPENDENT_SOURCE_AND_FORECAST_PROVENANCE_NOT_VERIFIED")
        self.assertFalse(report["positive_ev_verified"])

    def test_training_uses_only_settled_before_first_forecast(self):
        rows = fixtures()
        rows[0]["settled_at"] = (BASE + timedelta(days=5)).isoformat()
        report = walk_forward(rows, min_train=4, test_size=3)
        self.assertEqual(report["reason"], "TRAINING_RESULTS_UNAVAILABLE_AT_FORECAST")
        self.assertEqual(report["blocked_fold"], 1)
        self.assertEqual(report["available_train"], 3)

    def test_duplicate_event_holds(self):
        rows = fixtures()
        rows[-1]["event_id"] = rows[0]["event_id"]
        self.assertEqual(walk_forward(rows, min_train=4, test_size=3)["reason"],
                         "DUPLICATE_OR_INVALID_EVENT")

    def test_post_kickoff_forecast_holds(self):
        rows = fixtures()
        rows[7]["forecast_at"] = (BASE + timedelta(days=9)).isoformat()
        self.assertEqual(walk_forward(rows, min_train=4, test_size=3)["reason"],
                         "INVALID_EVENT_CHRONOLOGY")

    def test_non_chronological_holds(self):
        rows = fixtures()
        rows[3], rows[4] = rows[4], rows[3]
        self.assertEqual(walk_forward(rows, min_train=4, test_size=3)["reason"],
                         "NOT_CHRONOLOGICAL")

    def test_simultaneous_kickoff_not_split(self):
        rows = fixtures()
        rows[4]["kickoff_at"] = rows[3]["kickoff_at"]
        rows[4]["forecast_at"] = rows[3]["forecast_at"]
        rows[4]["settled_at"] = rows[3]["settled_at"]
        report = walk_forward(rows, min_train=4, test_size=3)
        self.assertEqual(report["fold_count"], 3)
        self.assertEqual(report["initial_training_count"], 5)
        self.assertEqual(report["evaluated_count"], 7)

    def test_malformed_probabilities_fail_entire_cohort(self):
        rows = fixtures()
        rows[10]["probabilities"] = {"H": 1., "D": .5, "A": -.5}
        self.assertEqual(walk_forward(rows, min_train=4, test_size=3)["status"], "HOLD")
        self.assertNotIn("folds", walk_forward(rows, min_train=4, test_size=3))

    def test_invalid_window_spec_holds(self):
        self.assertEqual(walk_forward(fixtures(), min_train=True, test_size=3)["reason"],
                         "INVALID_WINDOW_SPEC")

    def test_future_result_may_join_later_fold_only(self):
        rows = fixtures()
        # The final match of initial training is unavailable for fold 1,
        # so a stricter minimum forces HOLD; never silently exclude it.
        rows[3]["settled_at"] = (BASE + timedelta(days=6)).isoformat()
        self.assertEqual(walk_forward(rows, min_train=4, test_size=3)["reason"],
                         "TRAINING_RESULTS_UNAVAILABLE_AT_FORECAST")


if __name__ == "__main__":
    unittest.main()
