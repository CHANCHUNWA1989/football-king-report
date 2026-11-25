import unittest
from ops.complete_market_snapshot_research import audit


def snapshot():
    return {"fixture_id":"synthetic","provider":"provider","provider_event_id":"native",
            "bookmaker":"example","market":"h2h","observed_utc":"2026-11-25T10:00:00Z",
            "captured_utc":"2026-11-25T10:00:30Z","kickoff_utc":"2026-11-25T12:00:00Z",
            "prices":{"HOME":2.0,"DRAW":3.5,"AWAY":4.0},
            "production_recommendations":"DISABLED"}


class CompleteMarketSnapshotTests(unittest.TestCase):
    def test_proportional_normalization(self):
        r=audit(snapshot(),"2026-11-25T10:02:00Z")
        self.assertAlmostEqual(r["overround"],1/2+1/3.5+1/4-1)
        self.assertAlmostEqual(sum(r["proportional_no_vig_probabilities"].values()),1)
        self.assertAlmostEqual(r["proportional_fair_decimal_odds"]["HOME"],(1/2+1/3.5+1/4)*2)
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["executable_prices_authenticated"])

    def test_stale_future_and_postkickoff(self):
        for time in ("2026-11-25T10:02:01Z","2026-11-25T10:00:29Z","2026-11-25T12:00:00Z"):
            self.assertNotIn("overround",audit(snapshot(),time))

    def test_incomplete_or_invalid_prices(self):
        for prices in ({"HOME":2.0,"DRAW":3.5},{"HOME":True,"DRAW":3.5,"AWAY":4.0},
                       {"HOME":float("nan"),"DRAW":3.5,"AWAY":4.0},
                       {"HOME":5.0,"DRAW":5.0,"AWAY":5.0},
                       {"HOME":1.1,"DRAW":1.1,"AWAY":1.1}):
            self.assertNotIn("overround",audit(snapshot()|{"prices":prices},"2026-11-25T10:01:00Z"))

    def test_no_asian_price_inference(self):
        for market in ("spreads","totals"):
            r=audit(snapshot()|{"market":market},"2026-11-25T10:01:00Z")
            self.assertNotIn("proportional_no_vig_probabilities",r)

    def test_untrusted_certification_rejected(self):
        r=audit(snapshot()|{"verified":True},"2026-11-25T10:01:00Z")
        self.assertEqual(r["reason"],"INVALID_OR_UNSUPPORTED_SNAPSHOT")


if __name__=="__main__":
    unittest.main()
