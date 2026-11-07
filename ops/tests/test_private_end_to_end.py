"""Full synthetic quote -> refit -> forecast -> private aggregate smoke.

All identities, prices and outcomes are synthetic. No real betting claims.
"""
import unittest
from datetime import datetime, timedelta, timezone
from ops.private_h2h_evidence import bind_response, FEED_SCHEMA
from ops.private_live_refit import build
from ops.private_pair_aggregate import aggregate


class FakeGrid:
    home_draw_away = (0.5, 0.3, 0.2)


class FakeModel:
    fitted = 0

    def __init__(self, home_goals, away_goals, home_teams, away_teams):
        self.__class__.fitted += 1

    def fit(self):
        pass

    def predict(self, home, away, **kwargs):
        return FakeGrid()


class PrivateEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
        kickoff = self.now + timedelta(hours=2)
        event = {
            "id": "synthetic-target-1", "sport_key": "soccer_epl",
            "home_team": "Home", "away_team": "Away",
            "commence_time": kickoff.isoformat(),
            "bookmakers": [{"key": "synthetic-book",
                            "markets": [{"key": "h2h",
                                         "last_update": (self.now-timedelta(minutes=2)).isoformat(),
                                         "outcomes": [{"name": "Home", "price": 2.1},
                                                      {"name": "Draw", "price": 3.3},
                                                      {"name": "Away", "price": 3.4}]}]}]
        }
        bound = bind_response([event], league="epl", sport="soccer_epl", captured=self.now)
        self.assertEqual(len(bound["quotes"]), 3)
        self.feed = {"schema": FEED_SCHEMA, "production_recommendations": "DISABLED",
                     "quotes": bound["quotes"]}
        self.history = []
        for i in range(48):
            when = self.now - timedelta(days=60-i)
            home, away = ("Home", "Away") if i % 2 else ("Away", "Home")
            self.history.append({
                "source_namespace": "the_odds_api_v4", "event_id": f"synthetic-history-{i}",
                "league_id": "epl", "home_team_id": home, "away_team_id": away,
                "kickoff_utc": when.isoformat(),
                "result_recorded_utc": (when+timedelta(hours=3)).isoformat(),
                "home_goals": i % 3, "away_goals": i % 2
            })
        FakeModel.fitted = 0

    def test_end_to_end_research_only_and_redacted(self):
        result = build(self.feed, self.history, now=self.now, model_factory=FakeModel)
        self.assertEqual(result["status"], "RESEARCH_ONLY", result)
        self.assertEqual(FakeModel.fitted, 1)
        self.assertEqual(len(result["forecasts"]), 1)
        self.assertLess(datetime.fromisoformat(result["forecasts"][0]["forecast_utc"]), self.now)
        aggregate_report = aggregate(self.feed, result["forecasts"], now=self.now)
        self.assertEqual(aggregate_report["status"], "HOLD")
        self.assertEqual(aggregate_report["paired_research_quote_count"], 3)
        self.assertFalse(aggregate_report["positive_ev_verified"])
        self.assertFalse(aggregate_report["candidate_details_exported"])
        self.assertFalse(aggregate_report["raw_odds_exported"])
        self.assertNotIn("unverified_research_candidates", aggregate_report)
        self.assertNotIn("fixture_id", aggregate_report)
        self.assertNotIn("decimal_odds", aggregate_report)

    def test_delayed_runner_excludes_post_quote_result(self):
        # Quote was captured at now; a later runner may see newer results.
        # Refit must use the quote capture cutoff, not the delayed runner clock.
        delayed = self.now + timedelta(minutes=5)
        self.history[-1]["result_recorded_utc"] = (self.now + timedelta(minutes=1)).isoformat()
        result = build(self.feed, self.history, now=delayed, model_factory=FakeModel)
        self.assertEqual(result["status"], "RESEARCH_ONLY", result)
        self.assertEqual(result["forecasts"][0]["training_match_count"], 47)
        self.assertEqual(FakeModel.fitted, 1)

    def test_wrong_source_fails_closed(self):
        for row in self.history:
            row["source_namespace"] = "unmatched_provider"
        result = build(self.feed, self.history, now=self.now, model_factory=FakeModel)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["forecasts"], [])
        self.assertEqual(FakeModel.fitted, 0)

    def test_unavailable_results_fail_closed(self):
        for row in self.history:
            row["result_recorded_utc"] = (self.now+timedelta(minutes=1)).isoformat()
        result = build(self.feed, self.history, now=self.now, model_factory=FakeModel)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["forecasts"], [])
        self.assertEqual(FakeModel.fitted, 0)


if __name__ == "__main__":
    unittest.main()
