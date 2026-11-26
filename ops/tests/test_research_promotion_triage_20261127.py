import unittest
from copy import deepcopy
from ops.research_promotion_triage_20261127 import triage,METRICS

def packet():
    return {"cohort_sha256":"a"*64,"manifest_sha256":"b"*64,
            "forecast_archive_sha256":"c"*64,"settlement_archive_sha256":"d"*64,
            "retrospective_only":False,"comparator_role":"CURRENT_PRODUCTION",
            "baseline_id":"baseline","challenger_id":"challenger",
            "frozen_at":"2026-01-01T00:00:00Z","first_decision_at":"2026-01-02T00:00:00Z",
            "last_decision_at":"2026-09-01T00:00:00Z","evaluated_at":"2026-09-02T00:00:00Z",
            "n":500,"weeks":30,"complete_paired_cohort":True,"preregistered_primary":"log_loss",
            "multiplicity_controlled":True,"independent_reproduction":True,
            "deltas":{m:-.01 for m in METRICS},"intervals":{m:[-.02,-.001] for m in METRICS}}

class PromotionTriageTests(unittest.TestCase):
    def test_never_authorizes(self):
        r=triage(packet(),[])
        self.assertEqual(r["status"],"REVIEW_REQUIRED")
        self.assertFalse(r["promotion_authorized"])
        self.assertFalse(r["attestation_verified"])
        self.assertEqual(r["deployment"],"HOLD")
        self.assertEqual(r["recommendations"],"DISABLED")
    def test_reuse(self):
        self.assertIn("REUSED_COHORT",triage(packet(),["a"*64])["reasons"])
    def test_missing_each_required_field(self):
        for key in packet():
            with self.subTest(key=key):
                p=packet();p.pop(key)
                self.assertEqual(triage(p,[])["status"],"HOLD")
    def test_guardrails(self):
        for m in METRICS:
            for delta,ci in [(.01,[-.01,.02]),(-.01,[-.02,.001]),(float("nan"),[-.02,0]),(-.01,[0,-.02])]:
                p=packet();p["deltas"][m]=delta;p["intervals"][m]=ci
                self.assertEqual(triage(p,[])["status"],"HOLD")
        p=packet();p["deltas"]["log_loss"]=-.001
        self.assertIn("PRIMARY_IMPROVEMENT_UNPROVEN",triage(p,[])["reasons"])
    def test_retrospective(self):
        p=packet();p.update(retrospective_only=True,comparator_role="RESEARCH",
                           independent_reproduction=False)
        r=triage(p,[])
        self.assertIn("RETROSPECTIVE_OR_UNKNOWN",r["reasons"])
        self.assertIn("PRODUCTION_COMPARATOR_MISSING",r["reasons"])
        self.assertIn("REPRODUCTION_UNVERIFIED",r["reasons"])
    def test_invalid(self):
        self.assertEqual(triage(None,[])["status"],"HOLD")
        self.assertEqual(triage(packet(),["bad"])["status"],"HOLD")
        p=packet();p["frozen_at"]=p["first_decision_at"]
        self.assertIn("CHRONOLOGY_INVALID",triage(p,[])["reasons"])

if __name__=="__main__": unittest.main()
