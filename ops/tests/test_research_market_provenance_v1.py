import unittest
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote,audit_quotes

class MarketProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
    def quote(self,source="feed-a",**kwargs):
        fields=dict(source=source,bookmaker="book-1",event_id="fixture-1",
                    market="totals",selection="over",line=2.5,decimal_odds=1.91,
                    observed_at=self.now-timedelta(seconds=30),
                    kickoff_at=self.now+timedelta(hours=1))
        fields.update(kwargs)
        return Quote(**fields)
    def test_independent_sources(self):
        r=audit_quotes([self.quote(),self.quote("feed-b")],now=self.now)
        self.assertEqual(len(r["independent_market_keys"]),1)
        self.assertFalse(r["verified_executable_ev"])
    def test_duplicate_source_not_independent(self):
        r=audit_quotes([self.quote(),self.quote()],now=self.now)
        self.assertEqual(r["independent_market_keys"],[])
    def test_stale_quote_rejected(self):
        q=self.quote(observed_at=self.now-timedelta(hours=1))
        r=audit_quotes([q],now=self.now)
        self.assertEqual(r["rejected"][0]["reason"],"STALE_QUOTE")
    def test_post_kickoff_rejected(self):
        q=self.quote(kickoff_at=self.now-timedelta(seconds=1))
        r=audit_quotes([q],now=self.now)
        self.assertEqual(r["rejected"][0]["reason"],"NOT_PREMATCH")
    def test_wrong_line_rejected(self):
        r=audit_quotes([self.quote(line=2.3)],now=self.now)
        self.assertEqual(r["rejected"][0]["reason"],"INVALID_LINE")
    def test_never_production(self):
        r=audit_quotes([self.quote(is_executable=True)],now=self.now)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertFalse(r["qualified_for_production"])
if __name__=="__main__":unittest.main()
