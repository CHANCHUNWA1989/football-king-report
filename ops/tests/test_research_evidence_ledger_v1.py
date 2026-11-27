import unittest
from datetime import datetime,timedelta,timezone
from ops.research_evidence_ledger_v1 import research_evidence_record,verify_record
from ops.research_market_provenance_v1 import Quote

class EvidenceLedgerTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
        self.kickoff=self.now+timedelta(hours=1)
    def record(self,**kw):
        d=dict(event_id="fixture-a",forecast_at=self.now-timedelta(minutes=2),
               kickoff_at=self.kickoff,home_xg=1.4,away_xg=1.1,
               quotes=[],now=self.now,handicap_line=-0.25,totals_line=2.5,
               handicap_home_odds=1.9,handicap_away_odds=1.9,
               over_odds=1.9,under_odds=1.9)
        d.update(kw)
        return research_evidence_record(**d)
    def test_deterministic_digest(self):
        a=self.record()
        b=self.record()
        self.assertEqual(a["sha256"],b["sha256"])
        self.assertTrue(verify_record(a))
    def test_tamper_detection(self):
        r=self.record()
        r["one_x_two"]["home"]=0.99
        self.assertFalse(verify_record(r))
    def test_wrong_event_rejected(self):
        q=Quote("a","b","other","totals","over",2.5,1.9,self.now,self.kickoff)
        with self.assertRaises(ValueError):self.record(quotes=[q])
    def test_after_kickoff_rejected(self):
        with self.assertRaises(ValueError):self.record(now=self.kickoff)
    def test_fail_closed(self):
        r=self.record()
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["verified_positive_ev"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
if __name__=="__main__":unittest.main()
