import unittest
from datetime import datetime, timezone, timedelta
from ops.all_market_screen import screen

NOW = datetime(2026, 10, 10, 10, tzinfo=timezone.utc)
def quote(**kwargs):
    q = {"fixture_id": "fixture-1", "market": "asian_handicap", "selection": "home",
         "line": -1.25, "decimal_odds": 2.1, "source": "example",
         "observed_utc": (NOW-timedelta(minutes=2)).isoformat(),
         "kickoff_utc": (NOW+timedelta(hours=2)).isoformat()}
    q.update(kwargs)
    return q

class TestAllMarketScreen(unittest.TestCase):
    def test_missing_probability_is_research_only(self):
        self.assertEqual(screen({"quotes": [quote()]}, NOW)["candidates"][0]["status"], "RESEARCH_ONLY")
    def test_half_settlement_ev(self):
        q = quote(settlement_probabilities={"full_win": .4, "half_win": .2, "push": 0,
                                            "half_loss": .1, "full_loss": .3},
                  independently_calibrated=True, lineup_checked=True, source_verified=True)
        item = screen({"quotes": [q]}, NOW)["candidates"][0]
        self.assertAlmostEqual(item["ev_per_unit"], .2)
        self.assertEqual(item["status"], "RESEARCH_ONLY")\n        self.assertEqual(item["reason"], "INDEPENDENT_CERTIFICATION_GATE_NOT_IMPLEMENTED")
    def test_stale_quote(self):
        item = screen({"quotes": [quote(observed_utc=(NOW-timedelta(hours=1)).isoformat())]}, NOW)["candidates"][0]
        self.assertEqual(item["status"], "STALE")
    def test_reject_postkickoff(self):
        item = screen({"quotes": [quote(kickoff_utc=(NOW-timedelta(minutes=1)).isoformat())]}, NOW)["candidates"][0]
        self.assertEqual(item["status"], "INVALID")
    def test_all_market_types_not_filtered(self):
        q = [quote(market=m, selection=s) for m,s in [("asian_handicap","away"),("totals","over"),("totals","under"),("h2h","home"),("btts","yes")]]
        self.assertEqual(len(screen({"quotes":q}, NOW)["candidates"]), 5)

if __name__ == "__main__":
    unittest.main()
