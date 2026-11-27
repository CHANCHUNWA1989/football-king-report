import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from ops.research_unified_prematch_audit_v34 import Forecast,audit
from ops.research_market_provenance_v1 import Quote

class AuditV34(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,27,12,tzinfo=timezone.utc)
        self.kick=self.now+timedelta(hours=3)
        self.fs=[Forecast("e",self.kick,self.now,"m"+str(i),"f"+str(i),1.5+i*.1,1.1) for i in range(2)]
        self.qs=[Quote("p"+str(i),"book","e",m,s,l,1.9,self.now,self.kick,
                       upstream_provider="u"+str(i))
                 for m,s,l in [("handicap","home",-.25),("handicap","away",-.25),
                               ("totals","over",2.75),("totals","under",2.75)] for i in range(2)]
    def run_audit(self,**kw):
        args=dict(event_id="e",kickoff=self.kick,now=self.now,forecasts=self.fs,
                  quotes=self.qs,handicap_line=-.25,totals_line=2.75)
        args.update(kw)
        r=audit(**args)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertFalse(r["verified_executable_ev"])
        return r
    def test_valid_grid(self):
        r=self.run_audit()
        self.assertTrue(r["audit_completed"])
        self.assertEqual(r["scenario_count"],18)
        self.assertEqual(len(r["diagnostics"]),4)
        for d in r["diagnostics"].values():
            self.assertLessEqual(d["min"],d["max"])
            self.assertEqual(d["count"],18)
    def test_duplicate_lineage(self):
        self.assertFalse(self.run_audit(forecasts=[self.fs[0],replace(self.fs[1],upstream="F0")])["audit_completed"])
    def test_wrong_event(self):
        self.assertFalse(self.run_audit(forecasts=[self.fs[0],replace(self.fs[1],event_id="other")])["audit_completed"])
    def test_future_forecast(self):
        self.assertFalse(self.run_audit(forecasts=[self.fs[0],replace(self.fs[1],observed=self.now+timedelta(seconds=1))])["audit_completed"])
    def test_stale_quotes(self):
        self.assertFalse(self.run_audit(quotes=[replace(q,observed_at=self.now-timedelta(seconds=301)) for q in self.qs])["audit_completed"])
    def test_wrong_kickoff(self):
        self.assertFalse(self.run_audit(quotes=[replace(self.qs[0],kickoff_at=self.kick+timedelta(days=1))]+self.qs[1:])["audit_completed"])
    def test_missing_market(self):
        self.assertFalse(self.run_audit(quotes=self.qs[:-2])["audit_completed"])
    def test_invalid_delta(self):
        self.assertFalse(self.run_audit(delta=float("nan"))["audit_completed"])
    def test_post_kickoff(self):
        self.assertFalse(self.run_audit(now=self.kick)["audit_completed"])

if __name__=="__main__":
    unittest.main()
