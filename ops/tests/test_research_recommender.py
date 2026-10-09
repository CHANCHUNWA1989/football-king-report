"""Football King explainable picks: functional, strict time safety, graceful abstention."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_recommender import build, MAX_RESEARCH_SELECTIONS


class ResearchRecommendationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 6, tzinfo=timezone.utc)
        self.kickoff = (self.now + timedelta(days=2)).isoformat()
        self.shadow = {
            "status": "SHADOW_ONLY",
            "as_of_utc": (self.now-timedelta(minutes=2)).isoformat(),
            "production_recommendations": "DISABLED",
        }
        self.status = {
            "status": "RESEARCH_ONLY",
            "production_recommendations": "DISABLED"
        }
        self.sample = {
            "case_id": "case-1",
            "league": "bundesliga", "home": "Bayern", "away": "Dortmund",
            "kickoff_utc": self.kickoff,
            "prediction_utc": self.shadow["as_of_utc"],
            "market_snapshot_utc": (self.now-timedelta(minutes=20)).isoformat(),
            "market_updated_utc": (self.now-timedelta(minutes=25)).isoformat(),
            "model": [0.65, 0.20, 0.15],
            "market": [0.56, 0.25, 0.19],
            "result": None, "historical_outcome": None,
            "available_for_betting": False,
            "production_recommendations": "DISABLED"
        }
        self.pairing = {"status":"RESEARCH_ONLY","comparisons":[self.sample],
                        "production_recommendations":"DISABLED"}

    def run_engine(self):
        return build(self.shadow, self.pairing, self.status, now=self.now)

    def test_explainable_model_selection_visible(self):
        value = self.run_engine()
        self.assertEqual(value["status"], "RESEARCH_ONLY")
        self.assertEqual(value["selected_count"],1)
        one=value["selections"][0]
        self.assertEqual(one["direction_zh"], "主勝")
        self.assertTrue(one["market_direction_agrees"])
        self.assertGreaterEqual(len(one["reasons"]),3)
        self.assertEqual(one["reliability"],"UNCALIBRATED_RESEARCH_ONLY")
        self.assertFalse(one["value_bet_verified"])
        self.assertIsNone(one["suggested_stake"])
        self.assertEqual(one["production_recommendations"],"DISABLED")
        self.assertFalse(value["validated_positive_expected_value"])
        self.assertFalse(value["automatic_bets"])

    def test_draw_can_be_a_research_direction(self):
        self.sample["model"]=[0.29,0.52,0.19]
        self.sample["market"]=[0.30,0.48,0.22]
        item=self.run_engine()["selections"][0]
        self.assertEqual(item["direction"],"DRAW")

    def test_away_can_be_research_direction(self):
        self.sample["model"]=[0.13,0.22,0.65]
        self.sample["market"]=[0.15,0.26,0.59]
        self.assertEqual(self.run_engine()["selections"][0]["direction_zh"],"客勝")

    def test_market_disagreement_is_review_only(self):
        self.sample["market"]=[0.2,0.25,0.55]
        out=self.run_engine()
        self.assertEqual(out["selected_count"],0)
        self.assertEqual(out["review_count"],1)
        self.assertFalse(out["reviews"][0]["market_direction_agrees"])

    def test_too_close_probabilities_not_forced(self):
        self.sample["model"]=[0.43,0.32,0.25]
        self.sample["market"]=[0.44,0.35,0.21]
        out=self.run_engine()
        self.assertEqual(out["selected_count"],0)
        self.assertEqual(out["review_count"],1)

    def test_market_after_prediction_rejected(self):
        self.sample["market_snapshot_utc"] = (self.now+timedelta(minutes=1)).isoformat()
        self.assertEqual(self.run_engine()["selected_count"],0)
        self.assertEqual(self.run_engine()["excluded_reasons"]["MARKET_LATER_THAN_PREDICTION"],1)

    def test_past_market_quote_only(self):
        self.sample["market_updated_utc"]=(self.now+timedelta(minutes=10)).isoformat()
        out=self.run_engine()
        self.assertEqual(out["selected_count"],0)
        self.assertIn("MARKET_LATER_THAN_PREDICTION",out["excluded_reasons"])

    def test_stale_market_rejected(self):
        self.sample["market_updated_utc"]=(self.now-timedelta(hours=17)).isoformat()
        out=self.run_engine()
        self.assertIn("STALE_MARKET",out["excluded_reasons"])
        self.assertEqual(out["selected_count"],0)

    def test_model_older_than_ten_hours_holds(self):
        self.shadow["as_of_utc"]=(self.now-timedelta(hours=11)).isoformat()
        out=self.run_engine()
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["reason"],"STALE_MODEL_SNAPSHOT")

    def test_no_betting_if_page_quality_hold(self):
        self.status["status"]="HOLD"
        out=self.run_engine()
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["selected_count"],0)

    def test_near_kickoff_rejected(self):
        self.sample["kickoff_utc"]=(self.now+timedelta(minutes=35)).isoformat()
        self.assertIn("KICKOFF_TOO_CLOSE",self.run_engine()["excluded_reasons"])

    def test_far_away_games_excluded(self):
        self.sample["kickoff_utc"]=(self.now+timedelta(days=9)).isoformat()
        self.assertIn("FIXTURE_TOO_FAR_AHEAD",self.run_engine()["excluded_reasons"])

    def test_duplicate_case_rejected(self):
        self.pairing["comparisons"].append(dict(self.sample))
        out=self.run_engine()
        self.assertEqual(out["selected_count"],1)
        self.assertEqual(out["excluded_reasons"].get("DUPLICATE_PAIR"),1)

    def test_limits_to_eight_ranked_candidates(self):
        rows=[]
        for i in range(12):
            new=dict(self.sample)
            new["case_id"]=f"case-{i}"
            new["home"]=f"Home {i}"
            rows.append(new)
        self.pairing["comparisons"]=rows
        out=self.run_engine()
        self.assertEqual(out["selected_count"],MAX_RESEARCH_SELECTIONS)
        self.assertEqual(len(out["selections"]),MAX_RESEARCH_SELECTIONS)

    def test_invalid_or_unverified_quote_never_selected(self):
        self.sample["market"]=[0.9,0.9,-0.8]
        self.assertEqual(self.run_engine()["selected_count"],0)
        self.sample["market"]=[.56,.25,.19]
        self.sample["available_for_betting"]=True
        self.assertEqual(self.run_engine()["selected_count"],0)


if __name__=="__main__":
    unittest.main()
