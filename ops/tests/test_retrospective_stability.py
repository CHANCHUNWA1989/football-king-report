"""Do not confuse historical confidence bands with prospective betting edge."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrospective_stability import audit, fixed_bin, publish


def scope(n, rate, lo, hi, gap=0.01):
    return {"statistics": {
        "original": {"top_choice_calibration_gap": gap},
        "coverage_at_confidence_cutoffs": [{
            "minimum_model_probability": 0.6, "selected": n,
            "hit_rate": rate, "hit_rate_wilson95": [lo, hi]
        }]
    }}


class StabilityAuditTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "schema": "football-king-historical-date-replay-v1",
            "evaluation_type": "RETROSPECTIVE_DATE_ONLY_REPLAY",
            "live_point_in_time_forecasts_verified": False,
            "betting_roi_estimable": False,
            "market_baseline_available": False,
            "automatic_model_promotion": False,
            "production_recommendations": "DISABLED",
            "development_season": "2024-25", "holdout_season": "2025-26",
            "upstream_archives": [{"league": "epl"}, {"league": "ligue1"}],
            "by_league": {
                "epl": {"2024-25": scope(60, .72, .59, .82),
                        "2025-26": scope(60, .68, .55, .78)},
                "ligue1": {"2024-25": scope(60, .72, .59, .82),
                           "2025-26": scope(50, .51, .38, .64)},
            },
        }

    def test_stable_and_unstable_are_both_research_only(self):
        out = audit(self.report)
        self.assertEqual(out["status"], "RESEARCH_ONLY")
        self.assertEqual(out["league_count"], 2)
        self.assertEqual(out["caution_league_count"], 1)
        observed = {x["league"]: x for x in out["leagues"]}
        self.assertEqual(observed["epl"]["assessment"], "SHADOW_MONITOR_ONLY")
        self.assertEqual(observed["ligue1"]["assessment"], "SHADOW_CAUTION")
        for case in observed.values():
            self.assertFalse(case["live_predictive_stability_proven"])
            self.assertFalse(case["real_time_market_edge_verified"])
            self.assertIn("NOT_EXECUTABLE_BET", case["recommendation"])
        self.assertFalse(out["can_generate_bet_recommendations"])
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_small_sample_drift_and_missing_ci_not_promoted(self):
        self.report["by_league"]["epl"]["2025-26"] = scope(8, .75, .39, .92)
        self.report["by_league"]["ligue1"]["2025-26"] = {
            "statistics": {"coverage_at_confidence_cutoffs": []}}
        out = audit(self.report)
        states = {x["league"]: x["assessment"] for x in out["leagues"]}
        self.assertEqual(states["epl"], "SHADOW_CAUTION")
        self.assertEqual(states["ligue1"], "INSUFFICIENT_REPLAY_EVIDENCE")
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_claim_of_verified_roi_invalidates_input(self):
        self.report["betting_roi_estimable"] = True
        out = audit(self.report)
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["leagues"], [])
        self.assertFalse(out["automatic_model_promotion"])

    def test_bad_probabilities_rejected(self):
        self.assertIsNone(fixed_bin({"coverage_at_confidence_cutoffs": [{
            "minimum_model_probability": .60, "selected": 400,
            "hit_rate": .67, "hit_rate_wilson95": [.72, .84],
        }]}))
        self.assertIsNone(fixed_bin({"coverage_at_confidence_cutoffs": [{
            "minimum_model_probability": .60, "selected": True,
            "hit_rate": .67, "hit_rate_wilson95": [.53, .77],
        }]}))

    def test_publish_missing_input_holds_and_writes_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "stability.json"
            result = publish(Path(temp) / "missing.json", output)
            self.assertEqual(result["status"], "HOLD")
            doc = json.loads(output.read_text())
            self.assertFalse(doc["model_probabilities_not_certified"] is False)
            self.assertFalse(doc["can_generate_bet_recommendations"])


if __name__ == "__main__":
    unittest.main()
