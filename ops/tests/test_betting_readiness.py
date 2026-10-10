"""A research direction is never interchangeable with an executable bet."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from betting_readiness import collect, publish


class BettingReadinessTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 5, tzinfo=timezone.utc)
        self.gate = {
            "schema": "football-king-production-qualification-1",
            "status": "HOLD", "ready_for_independent_review": False,
            "production_recommendations": "DISABLED",
            "settled_samples": 1,
            "conditions": {
                "at_least_300_settled_point_in_time_samples": False,
                "market_quotes_are_legally_executable_at_recommendation_time": False,
                "independent_manual_research_approval": False,
            },
        }
        self.case = {
            "case_id": "testcase", "league": "bundesliga",
            "home": "Bayern", "away": "Dortmund",
            "kickoff_utc": (self.now + timedelta(hours=3)).isoformat(),
            "prediction_utc": (self.now - timedelta(minutes=3)).isoformat(),
            "research_probability": 0.65, "direction": "HOME",
            "market_direction_agrees": True,
            "production_recommendations": "DISABLED",
            "value_bet_verified": False,
            "executable_market_odds_available": False,
            "qualifies_for_research_shortlist": True,
        }
        self.research = {
            "schema": "football-king-explainable-research-selections-v1",
            "as_of_utc": (self.now - timedelta(minutes=3)).isoformat(),
            "model_is_uncalibrated": True,
            "market_prices_are_not_executable": True,
            "value_recommendation_count": 0,
            "production_recommendations": "DISABLED",
            "selections": [self.case],
        }

    def test_paper_watchlist_never_becomes_betting_advice(self):
        report = collect(self.gate, self.research, now=self.now)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["paper_watchlist_count"], 1)
        self.assertEqual(report["high_probability_paper_count"], 1)
        case = report["paper_watchlist"][0]
        self.assertFalse(case["bet_eligible"])
        self.assertIsNone(case["estimated_ev"])
        self.assertFalse(case["model_probabilities_certified"])
        self.assertFalse(report["genuine_positive_expected_value_verified"])
        self.assertEqual(report["bet_recommendations"], [])
        self.assertEqual(report["suggested_stakes"], [])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertIn(
            "market_quotes_are_legally_executable_at_recommendation_time",
            report["failed_production_checks"])

    def test_forged_positive_ev_claim_or_production_gate_rejected(self):
        self.research["value_recommendation_count"] = 1
        self.assertEqual(collect(self.gate, self.research, now=self.now)[
            "paper_watchlist"], [])
        self.research["value_recommendation_count"] = 0
        self.gate["production_recommendations"] = "ENABLED"
        self.assertEqual(collect(self.gate, self.research, now=self.now)[
            "bet_recommendation_count"], 0)

    def test_stale_quote_snapshot_and_close_kickoff_do_not_pass(self):
        self.research["as_of_utc"] = (
            self.now - timedelta(hours=12)).isoformat()
        self.assertEqual(collect(self.gate, self.research, now=self.now)[
            "reason"], "STALE_RESEARCH_CANDIDATES")
        self.research["as_of_utc"] = self.now.isoformat()
        self.case["kickoff_utc"] = (
            self.now + timedelta(minutes=20)).isoformat()
        self.assertEqual(collect(self.gate, self.research, now=self.now)[
            "paper_watchlist_count"], 0)

    def test_bookmaker_decimal_price_in_research_is_not_taken_as_real(self):
        self.case["decimal_odds"] = 99.99
        report = collect(self.gate, self.research, now=self.now)
        self.assertEqual(report["bet_recommendation_count"], 0)
        self.assertIsNone(report["paper_watchlist"][0]["estimated_ev"])
        self.assertIsNone(report["paper_watchlist"][0][
            "required_licensed_bookmaker_price"])

    def test_market_direction_disagreement_remains_observation_only(self):
        self.case["market_direction_agrees"] = False
        self.assertEqual(collect(self.gate, self.research, now=self.now)[
            "paper_watchlist"], [])

    def test_missing_files_publish_hold(self):
        with tempfile.TemporaryDirectory() as root:
            result = publish(root)
            self.assertEqual(result["reason"],
                             "MISSING_OR_UNSAFE_RECOMMENDATION_EVIDENCE")
            saved = json.loads((Path(root) / "betting_readiness.json").read_text())
            self.assertFalse(saved["can_generate_bet_recommendations"]
                             if "can_generate_bet_recommendations" in saved
                             else bool(saved["bet_recommendations"]))


if __name__ == "__main__":
    unittest.main()
