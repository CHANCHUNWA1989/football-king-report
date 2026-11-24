"""Prospective home/away role coverage guards; frozen probabilities remain unchanged."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from role_history_quality import build as role_quality, verify as verify_role
from shadow_forecast import predict_league
from market_pair import pair
from research_recommender import build as recommend


class RoleHistoryQualityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)
        teams = ["A", "B", "C", "D", "E", "F"]
        self.history = [{
            "date": (self.now - timedelta(days=i+1)).date().isoformat(),
            "home": teams[i % 6], "away": teams[(i + 1) % 6],
            "score_ft": [1+(i % 2), int(i % 3 == 0)],
            "status": "FINISHED", "kickoff_utc": None,
        } for i in range(48)]
        self.future = {
            "date": "2026-10-10", "home": "A", "away": "B",
            "kickoff_utc": "2026-10-10T12:00:00+00:00",
            "event_id": "future-123",
            "status": "SCHEDULED", "score_ft": None,
        }

    def test_existing_frozen_probabilities_unchanged_and_role_counts_visible(self):
        result = predict_league(self.history+[self.future], "epl", self.now)
        self.assertEqual(len(result), 1)
        item = result[0]
        role = verify_role(item["role_sample_quality"])
        self.assertEqual(role["home_team_total_games"], 16)
        self.assertEqual(role["away_team_total_games"], 16)
        self.assertEqual(role["home_team_home_games"], 8)
        self.assertEqual(role["away_team_away_games"], 8)
        self.assertTrue(role["role_sample_sufficient_for_research"])
        self.assertFalse(role["model_calibration_verified"])
        self.assertFalse(role["eligible_for_betting"])
        self.assertEqual(item["production_recommendations"], "DISABLED")

    def test_total_appearances_do_not_hide_untrained_stadium_roles(self):
        # Each sparse team has 3 genuine prior matches, but all in the
        # WRONG venue role for the future fixture. The original 48-match
        # aggregate must not imply 3 home/away samples for these teams.
        history = [dict(row) for row in self.history]
        for i in range(3):
            history[i]["away"] = "SparseHome"
            history[i + 3]["home"] = "SparseAway"
        thin_fixture = dict(self.future, home="SparseHome", away="SparseAway",
                            event_id="thin-role-123")
        result = predict_league(history + [thin_fixture], "epl", self.now)
        self.assertEqual(len(result), 1)
        quality = verify_role(result[0]["role_sample_quality"])
        self.assertEqual(quality["home_team_total_games"], 3)
        self.assertEqual(quality["away_team_total_games"], 3)
        self.assertEqual(quality["home_team_home_games"], 0)
        self.assertEqual(quality["away_team_away_games"], 0)
        self.assertFalse(quality["role_sample_sufficient_for_research"])
        self.assertEqual(quality["status"], "THIN_ROLE_HISTORY_REVIEW_ONLY")
        self.assertAlmostEqual(sum(result[0][x] for x in ("p_home", "p_draw", "p_away")),
                               1, places=6)

    def test_fake_sufficient_status_and_impossible_counts_are_rejected(self):
        thin = role_quality(8,8,0,0)
        for invalid in (
            {**thin,"role_sample_sufficient_for_research":True},
            {**thin,"status":"ROLE_COVERAGE_RESEARCH_ONLY"},
            {**thin,"home_team_home_games":9},
            {**thin,"minimum_per_role_games":0},
            {**thin,"model_calibration_verified":True},
            {**thin,"eligible_for_betting":True},
            {**thin,"home_team_home_games":True},
            {**thin,"injected":"ignore-me"},
            [],
        ):
            with self.subTest(invalid=str(invalid)[:70]):
                with self.assertRaises(ValueError):
                    verify_role(invalid)

    def paired(self, role):
        forecast = {
            "event_id":"f-1", "league":"epl", "home":"Everton", "away":"Arsenal",
            "kickoff_utc": "2026-10-11T12:00:00+00:00",
            "prediction_utc": self.now.isoformat(),
            "p_home":.65,"p_draw":.2,"p_away":.15,
            "role_sample_quality":role,
            "production_recommendations":"DISABLED",
        }
        shadow = {"status":"SHADOW_ONLY","as_of_utc":self.now.isoformat(),
                  "predictions":[forecast],"production_recommendations":"DISABLED"}
        market = {"status":"RESEARCH_ONLY",
                  "as_of_utc":(self.now-timedelta(minutes=10)).isoformat(),
                  "events":[{
                      "league":"epl","home":"Everton","away":"Arsenal",
                      "source_event_id":"source-fixture-1",
                      "kickoff_utc":forecast["kickoff_utc"],
                      "market_last_update_utc":(self.now-timedelta(minutes=15)).isoformat(),
                      "p_home":.56,"p_draw":.25,"p_away":.19
                  }],"production_recommendations":"DISABLED"}
        return shadow, pair(shadow,market)

    def test_market_pair_preserves_unmodified_role_quality(self):
        quality=role_quality(8,8,4,3)
        shadow,paired=self.paired(quality)
        self.assertEqual(paired["matched_count"],1)
        self.assertEqual(paired["comparisons"][0]["role_sample_quality"],quality)
        self.assertEqual(shadow["predictions"][0]["role_sample_quality"],quality)

    def test_fake_role_coverage_prevents_pairing(self):
        forged={**role_quality(8,8,0,0),"role_sample_sufficient_for_research":True}
        _,paired=self.paired(forged)
        self.assertEqual(paired["matched_count"],0)
        self.assertEqual(paired["status"],"HOLD")
        self.assertEqual(paired["production_recommendations"],"DISABLED")

    def test_sparse_sample_becomes_review_even_with_model_market_alignment(self):
        shadow,paired=self.paired(role_quality(8,8,0,1))
        now=self.now+timedelta(minutes=20)
        result=recommend(shadow,paired,
                         {"status":"RESEARCH_ONLY","production_recommendations":"DISABLED"},
                         now=now)
        self.assertEqual(result["selected_count"],0)
        self.assertEqual(result["review_count"],1)
        self.assertEqual(result["diagnostics"]["thin_role_history_review"],1)
        case=result["reviews"][0]
        self.assertTrue(case["market_direction_agrees"])
        self.assertFalse(case["qualifies_for_research_shortlist"])
        self.assertTrue(case["thin_role_history_review"])
        self.assertFalse(case["value_bet_verified"])
        self.assertEqual(case["production_recommendations"],"DISABLED")

    def test_adequate_role_sample_keeps_old_nonbetting_research_rules(self):
        shadow,paired=self.paired(role_quality(8,8,4,3))
        result=recommend(shadow,paired,
                         {"status":"RESEARCH_ONLY","production_recommendations":"DISABLED"},
                         now=self.now+timedelta(minutes=20))
        self.assertEqual(result["selected_count"],1)
        self.assertFalse(result["selections"][0]["thin_role_history_review"])
        self.assertEqual(result["value_recommendation_count"],0)
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_no_market_fallback_cannot_resurrect_thin_role_forecast(self):
        shadow,_=self.paired(role_quality(8,8,0,1))
        # No usable paired market; lower-evidence fallback must not bypass
        # the actual role-sample veto on newly generated snapshots.
        forecast=shadow["predictions"][0]
        forecast.update(p_home=.70,p_draw=.17,p_away=.13)
        pairing={"status":"HOLD","comparisons":[],"production_recommendations":"DISABLED"}
        result=recommend(shadow,pairing,
                         {"status":"HOLD","production_recommendations":"DISABLED"},
                         now=self.now+timedelta(minutes=20))
        self.assertEqual(result["model_only_count"],0)
        self.assertEqual(result["value_recommendation_count"],0)
        self.assertEqual(result["production_recommendations"],"DISABLED")


if __name__=="__main__":
    unittest.main()
