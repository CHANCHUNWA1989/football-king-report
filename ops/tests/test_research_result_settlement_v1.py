import unittest
from datetime import datetime,timedelta,timezone
from ops.research_evidence_ledger_v1 import research_evidence_record
from ops.research_result_settlement_v1 import ResultEvidence,audit_settlement

class ResultSettlementTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
        self.kickoff=self.now+timedelta(hours=1)
        self.f=research_evidence_record(event_id="f1",
          forecast_at=self.now-timedelta(minutes=1),kickoff_at=self.kickoff,
          home_xg=1.4,away_xg=1.1,quotes=[],now=self.now,
          handicap_line=-0.25,totals_line=2.5,handicap_home_odds=1.9,
          handicap_away_odds=1.9,over_odds=1.9,under_odds=1.9)
    def result(self,pub,score=(2,1),**kw):
        d=dict(event_id="f1",publisher=pub,
               observed_at=self.kickoff+timedelta(hours=2),
               home_goals=score[0],away_goals=score[1],is_final=True)
        d.update(kw)
        return ResultEvidence(**d)
    def test_two_sources_settle(self):
        r=audit_settlement(self.f,[self.result("a"),self.result("b")])
        self.assertEqual(r["status"],"SETTLED_RESEARCH")
        self.assertEqual(r["final_score"],[2,1])
        self.assertGreaterEqual(r["brier"],0)
    def test_duplicate_source_holds(self):
        self.assertEqual(audit_settlement(self.f,[self.result("a"),self.result("a")])["status"],"HOLD")
    def test_conflict_holds(self):
        r=audit_settlement(self.f,[self.result("a"),self.result("b",score=(1,2))])
        self.assertEqual(r["status"],"HOLD")
    def test_tamper_rejected(self):
        self.f["event_id"]="tampered"
        with self.assertRaises(ValueError):audit_settlement(self.f,[self.result("a"),self.result("b")])
    def test_nonfinal_holds(self):
        r=audit_settlement(self.f,[self.result("a",is_final=False),self.result("b")])
        self.assertEqual(r["status"],"HOLD")
    def test_production_disabled(self):
        r=audit_settlement(self.f,[self.result("a"),self.result("b")])
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["asian_market_settlements"],"NOT_VERIFIED")
if __name__=="__main__":unittest.main()
