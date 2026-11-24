import copy
import unittest
from datetime import datetime, timedelta, timezone
from ops.private_forecast_quote_pair import SCHEMA, pair


class PrivatePairTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
        self.kickoff = (self.now + timedelta(hours=2)).isoformat()
        self.forecast = {"fixture_id": "fixture-1", "kickoff_utc": self.kickoff,
                         "forecast_utc": (self.now - timedelta(hours=1)).isoformat(),
                         "probabilities": {"H": .5, "D": .3, "A": .2},
                         "model_id": "offline-research-v1",
                         "source_authenticity_verified": False,
                         "independently_timestamped": False}
        self.quote = {"fixture_id": "fixture-1", "kickoff_utc": self.kickoff,
                      "observed_utc": (self.now - timedelta(minutes=3)).isoformat(),
                      "market": "h2h", "selection": "H", "decimal_odds": 2.2,
                      "source": "PRIVATE_BOOKMAKER", "quote_id": "private-1"}
        self.data = {"schema": SCHEMA, "production_recommendations": "DISABLED",
                     "forecasts": [self.forecast], "quotes": [self.quote]}

    def run_pair(self, data=None):
        return pair(self.data if data is None else data, now=self.now)

    def test_paired_research_ev_but_not_certified(self):
        result = self.run_pair()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["paired_research_quotes"], 1)
        self.assertEqual(result["unverified_research_candidates"][0]["research_ev_per_unit"], .1)
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["recommendation_ready"])
        self.assertNotIn("PRIVATE_BOOKMAKER", str(result))
        self.assertNotIn("2.2", str(result))

    def test_missing_quote(self):
        data = copy.deepcopy(self.data)
        data["quotes"] = []
        self.assertEqual(self.run_pair(data)["paired_research_quotes"], 0)

    def test_stale_quote(self):
        data = copy.deepcopy(self.data)
        data["quotes"][0]["observed_utc"] = (self.now - timedelta(hours=1)).isoformat()
        self.assertEqual(self.run_pair(data)["rejected_quote_counts"]["STALE_QUOTE"], 1)

    def test_mismatched_kickoff(self):
        data = copy.deepcopy(self.data)
        data["quotes"][0]["kickoff_utc"] = (self.now + timedelta(hours=3)).isoformat()
        self.assertEqual(self.run_pair(data)["rejected_quote_counts"]["INVALID_QUOTE"], 1)

    def test_duplicate_quote_fails_closed(self):
        data = copy.deepcopy(self.data)
        data["quotes"].append(copy.deepcopy(data["quotes"][0]))
        self.assertEqual(self.run_pair(data)["reason"], "DUPLICATE_OR_INVALID_QUOTE_ID")

    def test_self_certification_rejected(self):
        data = copy.deepcopy(self.data)
        data["forecasts"][0]["independently_timestamped"] = True
        self.assertEqual(self.run_pair(data)["reason"], "SELF_CERTIFIED_FORECAST")

    def test_post_kickoff_forecast_rejected(self):
        data = copy.deepcopy(self.data)
        data["forecasts"][0]["forecast_utc"] = self.kickoff
        self.assertEqual(self.run_pair(data)["reason"], "FORECAST_NOT_PREMATCH")

    def test_bad_probability_rejected(self):
        data = copy.deepcopy(self.data)
        data["forecasts"][0]["probabilities"]["H"] = .9
        self.assertEqual(self.run_pair(data)["reason"], "INVALID_PROBABILITIES")

    def test_unknown_market_rejected(self):
        data = copy.deepcopy(self.data)
        data["quotes"][0]["market"] = "totals"
        self.assertEqual(self.run_pair(data)["rejected_quote_counts"]["INVALID_QUOTE"], 1)

    def test_no_external_verified_claim(self):
        data = copy.deepcopy(self.data)
        data["production_recommendations"] = "ENABLED"
        self.assertEqual(self.run_pair(data)["reason"], "INVALID_CONTRACT")


if __name__ == "__main__":
    unittest.main()
