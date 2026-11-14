"""Conservative, outcome-blind home-favourite cohort warning integration tests."""
import copy
from datetime import datetime, timedelta, timezone
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from home_favourite_sentinel import assess, MIN_CASES, MAX_HOME_TOP_SHARE
from research_recommender import build


NOW=datetime(2026,11,8,3,tzinfo=timezone.utc)


def forecast(i, *, home_top=True, league="bundesliga"):
    return {
        "event_id": f"fixture-{i}",
        "league": league,
        "home": f"Home_{i}",
        "away": f"Away_{i}",
        "kickoff_utc": (NOW+timedelta(days=2)).isoformat(),
        "prediction_utc": (NOW-timedelta(minutes=2)).isoformat(),
        "p_home": .68 if home_top else .14,
        "p_draw": .18,
        "p_away": .14 if home_top else .68,
        "status": "SCHEDULED",
        "score_ft": None,
        "production_recommendations": "DISABLED",
    }


def candidates(n, home):
    return [forecast(i,home_top=(i<home)) for i in range(n)]


class HomeBiasSentinelTests(unittest.TestCase):
    def test_live_like_16_of_19_home_favourites_raise_risk_without_changing_probs(self):
        data=candidates(19,16)
        original=copy.deepcopy(data)
        report=assess(data)
        self.assertEqual(data,original)
        bundesliga=report["by_league"]["bundesliga"]
        self.assertEqual(bundesliga["home_top_forecasts"],16)
        self.assertEqual(bundesliga["valid_distinct_pre_match_forecasts"],19)
        self.assertAlmostEqual(bundesliga["home_top_share"],16/19,places=5)
        self.assertTrue(bundesliga["home_favourite_concentration_review"])
        self.assertFalse(bundesliga["fallback_model_only_watchlist_allowed"])
        self.assertFalse(report["calibration_or_prediction_uplift_proven"])
        self.assertEqual(report["production_recommendations"],"DISABLED")

    def test_exact_eighty_percent_is_not_a_warning(self):
        report=assess(candidates(10,8))["by_league"]["bundesliga"]
        self.assertEqual(report["home_top_share"],.8)
        self.assertFalse(report["home_favourite_concentration_review"])

    def test_small_sample_does_not_claim_safe_or_detected_bias(self):
        report=assess(candidates(9,9))["by_league"]["bundesliga"]
        self.assertFalse(report["sufficient_cohort_for_warning"])
        self.assertFalse(report["home_favourite_concentration_review"])

    def test_duplicate_future_rows_and_post_match_results_cannot_dilute_warning(self):
        sample=candidates(19,16)
        duplicates=[copy.deepcopy(sample[i]) for i in range(4)]
        leaks=[{**forecast(100+i,home_top=False), "score_ft":[0,5]} for i in range(6)]
        report=assess(sample+duplicates+leaks)["by_league"]["bundesliga"]
        self.assertEqual(report["valid_distinct_pre_match_forecasts"],19)
        self.assertEqual(report["excluded_unusable_or_duplicate_rows"],10)
        self.assertTrue(report["home_favourite_concentration_review"])

    def test_unsupported_league_and_nonfinite_forecast_cannot_hide_signal(self):
        sample=candidates(19,16)
        garbage={**forecast(100,home_top=False),"p_away":float("nan")}
        report=assess(sample+[garbage,forecast(101,home_top=False,league="mls")])
        self.assertTrue(report["by_league"]["bundesliga"]["home_favourite_concentration_review"])
        self.assertEqual(report["by_league"]["bundesliga"]["excluded_unusable_or_duplicate_rows"],1)
        self.assertNotIn("mls",report["by_league"])

    def test_league_scoping_prevents_comparison_mixing(self):
        rows=candidates(12,11)+[forecast(i+50,home_top=False,league="epl") for i in range(20)]
        result=assess(rows)["by_league"]
        self.assertTrue(result["bundesliga"]["home_favourite_concentration_review"])
        self.assertFalse(result["epl"]["home_favourite_concentration_review"])

    def run_recommendations(self, predictions, paired=None):
        model={"status":"SHADOW_ONLY","as_of_utc":(NOW-timedelta(minutes=2)).isoformat(),
               "predictions":predictions,"production_recommendations":"DISABLED"}
        pairing={"status":"RESEARCH_ONLY" if paired else "HOLD",
                 "comparisons":paired or [],"production_recommendations":"DISABLED"}
        status={"status":"RESEARCH_ONLY","production_recommendations":"DISABLED"}
        return build(model,pairing,status,now=NOW)

    def test_skew_quarantines_all_unmarketed_model_only_observations(self):
        report=self.run_recommendations(candidates(19,16))
        self.assertEqual(report["fallback_mode"],"MODEL_ONLY_LOW_EVIDENCE")
        self.assertEqual(report["model_only_count"],0)
        self.assertEqual(report["diagnostics"]["home_bias_model_only_watchlist_blocked"],19)
        self.assertTrue(report["diagnostics"]["home_favourite_cohort_risk"]
                        ["by_league"]["bundesliga"]
                        ["home_favourite_concentration_review"])
        self.assertEqual(report["value_recommendation_count"],0)
        self.assertEqual(report["production_recommendations"],"DISABLED")

    def test_normal_cohort_retains_unmarketed_research_only_watchlist(self):
        report=self.run_recommendations(candidates(10,8))
        self.assertEqual(report["model_only_count"],5)
        self.assertEqual(report["diagnostics"]["home_bias_model_only_watchlist_blocked"],0)
        self.assertFalse(report["diagnostics"]["home_favourite_cohort_risk"]
                         ["by_league"]["bundesliga"]
                         ["home_favourite_concentration_review"])
        self.assertFalse(report["model_only_watchlist"][0]["qualifies_for_betting"])

    def test_paired_market_research_remains_unchanged_by_unmarketed_cohort_gate(self):
        pred=candidates(19,16)
        first=pred[0]
        pairing=[{
            "case_id":"market-case-0","league":"bundesliga",
            "home":first["home"],"away":first["away"],
            "kickoff_utc":first["kickoff_utc"],
            "prediction_utc":first["prediction_utc"],
            "market_snapshot_utc":(NOW-timedelta(minutes=20)).isoformat(),
            "market_updated_utc":(NOW-timedelta(minutes=25)).isoformat(),
            "model":[.68,.18,.14],"market":[.61,.22,.17],
            "production_recommendations":"DISABLED",
            "available_for_betting":False
        }]
        report=self.run_recommendations(pred,paired=pairing)
        self.assertEqual(report["selected_count"],1)
        self.assertEqual(report["model_only_count"],0)
        self.assertFalse(report["selections"][0]["value_bet_verified"])
        self.assertEqual(report["production_recommendations"],"DISABLED")


if __name__=="__main__":
    unittest.main()
