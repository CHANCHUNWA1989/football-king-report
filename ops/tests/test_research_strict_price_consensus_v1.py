import unittest
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote,audit_quotes

class StrictConsensusTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
    def q(self,source,upstream,**kwargs):
        fields=dict(source=source,upstream_provider=upstream,
            bookmaker="book-a",event_id="match",market="totals",
            selection="over",line=2.5,decimal_odds=1.91,
            observed_at=self.now-timedelta(seconds=120),
            kickoff_at=self.now+timedelta(hours=1))
        fields.update(kwargs)
        return Quote(**fields)
    def audit(self,a,b):
        return audit_quotes([a,b],now=self.now)
    def test_exact_consensus(self):
        r=self.audit(self.q("a","up-a"),self.q("b","up-b"))
        self.assertEqual(len(r["strict_price_consensus"]),1)
        self.assertFalse(r["verified_executable_ev"])
    def test_price_mismatch(self):
        r=self.audit(self.q("a","up-a"),self.q("b","up-b",decimal_odds=1.92))
        self.assertEqual(r["strict_price_consensus"],[])
    def test_bookmaker_mismatch(self):
        r=self.audit(self.q("a","up-a"),self.q("b","up-b",bookmaker="book-b"))
        self.assertEqual(r["strict_price_consensus"],[])
    def test_timestamp_gap(self):
        r=self.audit(self.q("a","up-a"),
                     self.q("b","up-b",observed_at=self.now-timedelta(seconds=190)))
        self.assertEqual(r["strict_price_consensus"],[])
    def test_same_upstream(self):
        r=self.audit(self.q("a","up-a"),self.q("b","UP-A"))
        self.assertEqual(r["strict_price_consensus"],[])
if __name__=="__main__":unittest.main()
