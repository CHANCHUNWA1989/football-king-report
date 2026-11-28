import unittest
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote,audit_quotes

class UpstreamLineageTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
    def q(self,source,upstream_provider):
        return Quote(source=source,upstream_provider=upstream_provider,
            bookmaker="book-1",event_id="fixture-1",market="totals",
            selection="over",line=2.5,decimal_odds=1.9,
            observed_at=self.now-timedelta(seconds=30),
            kickoff_at=self.now+timedelta(hours=1))
    def audit(self,*quotes):
        return audit_quotes(quotes,now=self.now)
    def test_unknown_upstream_not_independent(self):
        r=self.audit(self.q("a",""),self.q("b",""))
        self.assertEqual(r["independent_market_keys"],[])
    def test_same_upstream_different_publishers(self):
        r=self.audit(self.q("a","Feed One"),self.q("b"," feed one "))
        self.assertEqual(r["independent_market_keys"],[])
    def test_same_publisher_alias_not_independent(self):
        r=self.audit(self.q("a","up-a"),self.q(" A ","up-b"))
        self.assertEqual(r["independent_market_keys"],[])
    def test_distinct_upstreams_and_publishers(self):
        r=self.audit(self.q("a","up-a"),self.q("b","up-b"))
        self.assertEqual(len(r["independent_market_keys"]),1)
        self.assertFalse(r["verified_executable_ev"])
    def test_missing_lineage_cannot_pass_with_one_known(self):
        r=self.audit(self.q("a","up-a"),self.q("b",""))
        self.assertEqual(r["independent_market_keys"],[])
if __name__=="__main__":unittest.main()
