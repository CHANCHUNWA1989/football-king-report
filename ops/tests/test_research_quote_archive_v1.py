import copy
import unittest
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_quote_archive_v1 import freeze_pricing_evidence,verify_pricing_evidence

class QuoteArchiveTests(unittest.TestCase):
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
    def freeze(self,quotes=None):
        return freeze_pricing_evidence(event_id="fixture",home_xg=1.5,
            away_xg=1.1,quotes=self.quotes if quotes is None else quotes,
            now=self.now,handicap_line=-0.25,totals_line=2.5)
    def test_roundtrip(self):
        record=self.freeze()
        self.assertTrue(verify_pricing_evidence(record))
        self.assertEqual(len(record["quotes"]),8)
        self.assertFalse(record["qualified_for_production"])
    def test_reproducible_order(self):
        self.assertEqual(self.freeze()["sha256"],self.freeze(list(reversed(self.quotes)))["sha256"])
    def test_price_tamper(self):
        r=self.freeze()
        r["quotes"][0]["decimal_odds"]=2.0
        self.assertFalse(verify_pricing_evidence(r))
    def test_model_tamper(self):
        r=self.freeze()
        r["model"]["home_xg"]=5.0
        self.assertFalse(verify_pricing_evidence(r))
    def test_pricing_tamper(self):
        r=self.freeze()
        r["pricing"]["qualified_for_production"]=True
        self.assertFalse(verify_pricing_evidence(r))
    def test_missing_market_rejected(self):
        with self.assertRaises(ValueError):self.freeze(self.quotes[:-2])
if __name__=="__main__":unittest.main()
