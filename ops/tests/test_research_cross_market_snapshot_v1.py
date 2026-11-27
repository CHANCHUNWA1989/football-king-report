import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_evidence_bound_pricing_v1 import evidence_bound_pricing

class CrossMarketSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
    def quotes(self,offsets=(20,20,20,20)):
        out=[]
        markets=(("handicap","home",-0.25),("handicap","away",-0.25),
                 ("totals","over",2.5),("totals","under",2.5))
        for (market,selection,line),seconds in zip(markets,offsets):
            for source,upstream in (("a","up-a"),("b","up-b")):
                out.append(Quote(source=source,upstream_provider=upstream,
                    bookmaker="book-a",event_id="fixture",market=market,
                    selection=selection,line=line,decimal_odds=1.91,
                    observed_at=self.now-timedelta(seconds=seconds),
                    kickoff_at=self.now+timedelta(hours=1)))
        return out
    def price(self,quotes):
        return evidence_bound_pricing(event_id="fixture",home_xg=1.5,
            away_xg=1.1,quotes=quotes,now=self.now,
            handicap_line=-0.25,totals_line=2.5)
    def test_coherent_snapshot_passes(self):
        self.assertEqual(len(self.price(self.quotes((20,35,45,60)))["markets"]),4)
    def test_cross_market_drift_fails(self):
        with self.assertRaisesRegex(ValueError,"cross-market"):
            self.price(self.quotes((20,20,20,120)))
    def test_boundary_sixty_seconds_passes(self):
        self.assertEqual(len(self.price(self.quotes((20,20,20,80)))["markets"]),4)
    def test_individual_freshness_not_sufficient(self):
        with self.assertRaisesRegex(ValueError,"cross-market"):
            self.price(self.quotes((20,80,140,200)))
if __name__=="__main__":unittest.main()
