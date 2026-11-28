import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_evidence_bound_pricing_v1 import evidence_bound_pricing

class PricingFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
        self.quotes=[]
        for market,selection,line in (
            ("handicap","home",-0.25),("handicap","away",-0.25),
            ("totals","over",2.5),("totals","under",2.5)):
            for source,upstream in (("a","up-a"),("b","up-b")):
                self.quotes.append(Quote(source=source,upstream_provider=upstream,
                    bookmaker="book-a",event_id="fixture",market=market,
                    selection=selection,line=line,decimal_odds=1.91,
                    observed_at=self.now-timedelta(seconds=20),
                    kickoff_at=self.now+timedelta(hours=1)))
    def price(self,quotes):
        return evidence_bound_pricing(event_id="fixture",home_xg=1.5,
            away_xg=1.1,quotes=quotes,now=self.now,
            handicap_line=-0.25,totals_line=2.5)
    def test_valid(self):
        self.assertEqual(len(self.price(self.quotes)["markets"]),4)
    def test_negative_odds_rejected(self):
        q=[replace(x,decimal_odds=-1) for x in self.quotes]
        with self.assertRaises(ValueError):self.price(q)
    def test_infinite_odds_rejected(self):
        q=[replace(x,decimal_odds=float("inf")) for x in self.quotes]
        with self.assertRaises(ValueError):self.price(q)
    def test_blank_source_rejected(self):
        q=[replace(x,source=" ") for x in self.quotes]
        with self.assertRaises(ValueError):self.price(q)
    def test_missing_upstream_rejected(self):
        q=[replace(x,upstream_provider="") for x in self.quotes]
        with self.assertRaises(ValueError):self.price(q)
if __name__=="__main__":unittest.main()
