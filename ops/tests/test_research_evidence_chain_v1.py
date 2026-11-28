import unittest
from datetime import datetime,timedelta,timezone
from ops.research_evidence_ledger_v1 import research_evidence_record
from ops.research_evidence_chain_v1 import append_evidence,verify_chain,chain_audit

class EvidenceChainTests(unittest.TestCase):
    def forecast(self,i):
        now=datetime(2026,11,27,12,tzinfo=timezone.utc)+timedelta(days=i)
        return research_evidence_record(event_id="f"+str(i),
            forecast_at=now-timedelta(minutes=1),kickoff_at=now+timedelta(hours=1),
            home_xg=1.4,away_xg=1.1,quotes=[],now=now,
            handicap_line=-0.25,totals_line=2.5,handicap_home_odds=1.9,
            handicap_away_odds=1.9,over_odds=1.9,under_odds=1.9)
    def test_append_and_verify(self):
        chain=[]
        for i in range(3):
            chain.append(append_evidence(chain,self.forecast(i)))
        self.assertTrue(verify_chain(chain))
        self.assertEqual(chain_audit(chain)["entries"],3)
    def test_modified_entry_fails(self):
        chain=[append_evidence([],self.forecast(0))]
        chain[0]["event_id"]="modified"
        self.assertFalse(verify_chain(chain))
    def test_duplicate_rejected(self):
        f=self.forecast(0)
        chain=[append_evidence([],f)]
        with self.assertRaises(ValueError):append_evidence(chain,f)
    def test_bad_forecast_rejected(self):
        f=self.forecast(0)
        f["one_x_two"]["home"]=0.99
        with self.assertRaises(ValueError):append_evidence([],f)
    def test_corrupt_chain_rejected(self):
        chain=[append_evidence([],self.forecast(0))]
        chain[0]["entry_sha256"]="0"*64
        with self.assertRaises(ValueError):append_evidence(chain,self.forecast(1))
    def test_no_external_anchor_claim(self):
        r=chain_audit([])
        self.assertFalse(r["external_anchor_verified"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
if __name__=="__main__":unittest.main()
