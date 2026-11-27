import unittest
from datetime import datetime,timedelta,timezone
from ops.research_evidence_ledger_v1 import research_evidence_record
from ops.research_result_settlement_v1 import ResultEvidence
from ops.research_evidence_oos_bridge_v1 import build_paired_evidence,evidence_oos_report

class EvidenceOOSBridgeTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
    def fixture(self,i=0):
        kickoff=self.now+timedelta(days=i,hours=1)
        def forecast(h,a):
            return research_evidence_record(
                event_id="f"+str(i),forecast_at=kickoff-timedelta(hours=2),
                kickoff_at=kickoff,home_xg=h,away_xg=a,quotes=[],
                now=kickoff-timedelta(hours=1),handicap_line=-0.25,
                totals_line=2.5,handicap_home_odds=1.9,
                handicap_away_odds=1.9,over_odds=1.9,under_odds=1.9)
        results=[ResultEvidence("f"+str(i),pub,kickoff+timedelta(hours=2),2,1,True)
                 for pub in ("official-a","official-b")]
        return forecast(1.3,1.1),forecast(1.6,1.0),results
    def test_evidence_to_paired(self):
        p=build_paired_evidence(*self.fixture())
        self.assertEqual(p.outcome,"home")
        self.assertTrue(p.independently_verified)
    def test_two_fixtures_report(self):
        r=evidence_oos_report([self.fixture(0),self.fixture(1)],minimum_samples=2)
        self.assertEqual(r["sample_count"],2)
        self.assertTrue(r["evidence_linked"])
        self.assertFalse(r["qualified_for_production"])
    def test_tamper_rejected(self):
        b,c,r=self.fixture()
        c["one_x_two"]["home"]=0.99
        with self.assertRaises(ValueError):build_paired_evidence(b,c,r)
    def test_one_source_rejected(self):
        b,c,r=self.fixture()
        with self.assertRaises(ValueError):build_paired_evidence(b,c,r[:1])
    def test_fixture_mismatch_rejected(self):
        b,_,r=self.fixture(0)
        _,c,_=self.fixture(1)
        with self.assertRaises(ValueError):build_paired_evidence(b,c,r)
    def test_duplicate_fixture_rejected(self):
        f=self.fixture()
        with self.assertRaises(ValueError):evidence_oos_report([f,f],minimum_samples=2)
if __name__=="__main__":unittest.main()
