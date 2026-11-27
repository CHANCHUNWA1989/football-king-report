import unittest
from datetime import datetime,timedelta,timezone
from ops.research_evidence_ledger_v1 import research_evidence_record
from ops.research_result_settlement_v1 import ResultEvidence,audit_settlement

class PublisherIdentityTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
        self.kickoff=self.now+timedelta(hours=1)
        self.forecast=research_evidence_record(
            event_id="fixture",forecast_at=self.now-timedelta(minutes=2),
            kickoff_at=self.kickoff,now=self.now,quotes=[],
            home_xg=1.5,away_xg=1.1,handicap_line=-0.25,totals_line=2.5,
            handicap_home_odds=1.9,handicap_away_odds=1.9,
            over_odds=1.9,under_odds=1.9)
    def result(self,publisher,h=2,a=1):
        return ResultEvidence("fixture",publisher,
            self.kickoff+timedelta(hours=2),h,a,True)
    def test_case_variant_not_independent(self):
        r=audit_settlement(self.forecast,[self.result("Official"),self.result(" official ")])
        self.assertEqual(r["status"],"HOLD")
    def test_conflicting_same_publisher_holds(self):
        r=audit_settlement(self.forecast,[
            self.result("a"),self.result("b"),self.result("A",1,2)])
        self.assertEqual(r["status"],"HOLD")
    def test_two_distinct_publishers_settle(self):
        r=audit_settlement(self.forecast,[self.result("a"),self.result("b")])
        self.assertEqual(r["status"],"SETTLED_RESEARCH")
        self.assertFalse(r["qualified_for_production"])
if __name__=="__main__":unittest.main()
