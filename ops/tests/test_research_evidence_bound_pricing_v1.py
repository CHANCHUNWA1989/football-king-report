import unittest
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_evidence_bound_pricing_v1 import evidence_bound_pricing

class EvidenceBoundPricingTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
    def quotes(self):
        out=[]
        for market,selection,line in [
            ("handicap","home",-0.25),("handicap","away",-0.25),
            ("totals","over",2.5),("totals","under",2.5)]:
            for source,upstream in (("a","up-a"),("b","up-b")):
                out.append(Quote(source=source,upstream_provider=upstream,
                    bookmaker="book-a",event_id="fixture",market=market,
                    selection=selection,line=line,decimal_odds=1.91,
                    observed_at=self.now-timedelta(seconds=20),
                    kickoff_at=self.now+timedelta(hours=1)))
        return out
    def run_pricing(self,quotes):
        return evidence_bound_pricing(event_id="fixture",home_xg=1.5,
            away_xg=1.1,quotes=quotes,now=self.now,
            handicap_line=-0.25,totals_line=2.5)
    def test_four_selections(self):
        r=self.run_pricing(self.quotes())
        self.assertEqual(len(r["markets"]),4)
        self.assertTrue(r["evidence_bound_research_prices"])
        self.assertFalse(r["verified_executable_ev"])
    def test_missing_selection(self):
        q=[x for x in self.quotes() if x.selection!="under"]
        with self.assertRaises(ValueError):self.run_pricing(q)
    def test_price_mismatch(self):
        q=self.quotes()
        from dataclasses import replace
        q[0]=replace(q[0],decimal_odds=1.93)
        with self.assertRaises(ValueError):self.run_pricing(q)
    def test_syndicated_feed(self):
        q=self.quotes()
        from dataclasses import replace
        q[0]=replace(q[0],upstream_provider="up-b")
        with self.assertRaises(ValueError):self.run_pricing(q)
    def test_wrong_event(self):
        with self.assertRaises(ValueError):
            evidence_bound_pricing(event_id="wrong",home_xg=1.5,
                away_xg=1.1,quotes=self.quotes(),now=self.now,
                handicap_line=-0.25,totals_line=2.5)
if __name__=="__main__":unittest.main()
