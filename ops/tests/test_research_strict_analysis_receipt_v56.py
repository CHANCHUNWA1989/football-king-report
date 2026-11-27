import copy
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from ops.research_unified_prematch_audit_v34 import Forecast
from ops.research_market_provenance_v1 import Quote
from ops.research_unified_prematch_replay_v35 import freeze,digest
from ops.research_strict_analysis_receipt_v56 import report,recheck

class StrictReceiptV56(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).resolve().parents[2]
        now=datetime(2026,11,27,12,tzinfo=timezone.utc)
        kick=now+timedelta(hours=3)
        fs=[Forecast("e",kick,now,"m"+str(i),"f"+str(i),1.5+i*.1,1.1) for i in range(2)]
        qs=[Quote("p"+str(i),"book","e",m,s,l,1.9,now,kick,upstream_provider="u"+str(i))
            for m,s,l in [("handicap","home",-.25),("handicap","away",-.25),
                          ("totals","over",2.75),("totals","under",2.75)] for i in range(2)]
        self.record=freeze(event_id="e",kickoff=kick,now=now,forecasts=fs,quotes=qs,
                           handicap_line=-.25,totals_line=2.75,root=self.root)
    def run_report(self,r=None):
        return report(self.record if r is None else r,root=self.root)
    def test_exact_grid_and_normalization(self):
        result=self.run_report()
        self.assertTrue(result["research_completed"])
        self.assertEqual(result["scenario_count"],36)
        self.assertEqual({r["rho"] for r in result["scenarios"]},{None,-.1})
        for r in result["scenarios"]:
            self.assertAlmostEqual(sum(r["one_x_two"].values()),1)
            self.assertEqual(len(r["scenario_returns"]),4)
        self.assertEqual(result["input_sha256"],self.record["sha256"])
    def test_deterministic_and_never_promoted(self):
        r=self.run_report()
        self.assertEqual(r,self.run_report())
        self.assertTrue(recheck(r,self.record,root=self.root))
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for key in ("verified_executable_ev","qualified_for_production","training_admission",
                    "public_output_allowed","calibrated","source_identity_authenticated"):
            self.assertIs(r[key],False)
    def test_forged_report_rejected_even_rehashed(self):
        r=self.run_report()
        r["probability_bounds"]["home"]["max"]=1
        r["sha256"]=digest({k:v for k,v in r.items() if k!="sha256"})
        self.assertFalse(recheck(r,self.record,root=self.root))
    def test_forged_input_suppresses_all_numbers(self):
        r=copy.deepcopy(self.record)
        r["forecasts"][0]["home"]=3
        r["sha256"]=digest({k:v for k,v in r.items() if k!="sha256"})
        result=self.run_report(r)
        self.assertFalse(result["research_completed"])
        self.assertNotIn("probability_bounds",result)
        self.assertNotIn("scenario_return_bounds",result)
    def test_invalid_payload(self):
        result=report({},root=self.root)
        self.assertFalse(result["research_completed"])
        self.assertFalse(recheck(result,{},root=self.root))
