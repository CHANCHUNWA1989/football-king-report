import unittest
from datetime import datetime,timedelta,timezone
from ops.research_evidence_ledger_v1 import research_evidence_record
from ops.research_result_settlement_v1 import ResultEvidence
from ops.research_batch_integrity_v1 import audit_evidence_batch

class BatchIntegrityTests(unittest.TestCase):
    def fixture(self,i):
        base=datetime(2026,11,27,tzinfo=timezone.utc)+timedelta(days=i)
        kick=base+timedelta(hours=3)
        def f(x):
            return research_evidence_record(event_id=str(i),forecast_at=base,
                kickoff_at=kick,home_xg=x,away_xg=1.0,quotes=[],
                now=base+timedelta(hours=1),handicap_line=0,totals_line=2.5,
                handicap_home_odds=1.9,handicap_away_odds=1.9,
                over_odds=1.9,under_odds=1.9)
        rs=[ResultEvidence(str(i),p,kick+timedelta(hours=2),2,1,True)
            for p in ("official-a","official-b")]
        return f(1.2),f(1.4),rs
    def test_reproducible_batch_hash(self):
        fixtures=[self.fixture(0),self.fixture(1)]
        a=audit_evidence_batch(fixtures,minimum_samples=2)
        b=audit_evidence_batch(fixtures,minimum_samples=2)
        self.assertEqual(a["batch_sha256"],b["batch_sha256"])
        self.assertEqual(a["sample_count"],2)
        self.assertEqual(a["status"],"HOLD")
    def test_duplicate_rejected(self):
        f=self.fixture(0)
        with self.assertRaises(ValueError):audit_evidence_batch([f,f])
    def test_reordered_rejected(self):
        with self.assertRaises(ValueError):audit_evidence_batch([self.fixture(1),self.fixture(0)])
    def test_publisher_conflict_holds(self):
        b,c,rs=self.fixture(0)
        rs.append(ResultEvidence("0","official-a",rs[0].observed_at,1,2,True))
        r=audit_evidence_batch([(b,c,rs)])
        self.assertEqual(r["reason"],"CONFLICTING_PUBLISHER_ATTESTATIONS")
        self.assertFalse(r["qualified_for_production"])
    def test_forecast_tamper_rejected(self):
        b,c,rs=self.fixture(0)
        b["model"]["home_xg"]=9
        with self.assertRaises(ValueError):audit_evidence_batch([(b,c,rs)])
if __name__=="__main__":unittest.main()
