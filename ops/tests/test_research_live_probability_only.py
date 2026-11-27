import json
import unittest
from ops.tests.test_research_unified_live_v2 import fixture,NOW
from ops.tests.test_research_live_evidence_v3 import final,FIN,evaluate_one,RELEASE
from ops.tests.test_research_live_intake_v4 import inputs
from ops.research_live_intake_v4 import intake
from ops.research_live_evidence_v3 import seal,verify_bundle,settle
from ops.research_unified_live_v2 import digest

class ProbabilityOnlyTests(unittest.TestCase):
    def test_seal_settle_score_without_market(self):
        s,p=fixture(); del s["quote"]
        b=seal(s,p,as_of=NOW,captured_at=NOW,model_release=RELEASE,probability_only=True)
        self.assertTrue(verify_bundle(b))
        self.assertEqual(b["market_evidence"],"ABSENT")
        self.assertNotIn("hypothetical_ev",b["report"])
        self.assertFalse(b["certified_ev"])
        e=evaluate_one([(b,settle(b,final(),as_of=FIN))])
        self.assertEqual(e["probability_only_count"],1)
        self.assertEqual(e["with_market_snapshot_count"],0)
        self.assertFalse(e["market_comparison_performed"])
        self.assertFalse(e["independent_oos_proven"])
    def test_default_requires_market(self):
        s,p=fixture(); del s["quote"]
        with self.assertRaises(ValueError):seal(s,p,as_of=NOW,captured_at=NOW,model_release=RELEASE)
    def test_explicit_mode_rejects_quote(self):
        s,p=fixture()
        with self.assertRaises(ValueError):seal(s,p,as_of=NOW,captured_at=NOW,model_release=RELEASE,probability_only=True)
    def test_cross_stream_skew(self):
        s,p=fixture(); del s["quote"]
        for r in s["stats"]:
            r.update(updated="2026-11-27T09:05:00Z",window_start="2026-11-27T08:55:00Z",
                     window_end="2026-11-27T09:05:00Z")
        with self.assertRaises(ValueError):seal(s,p,as_of=NOW,captured_at=NOW,model_release=RELEASE,probability_only=True)
    def test_intake_explicit(self):
        r,p=inputs(); r=[x for x in r if x["kind"]!="quote"]
        raw=[json.dumps(x).encode() for x in r]
        kwargs=dict(event_id="synthetic",as_of=NOW,model_release=RELEASE)
        self.assertFalse(intake(raw,p,**kwargs)["structural_intake_passed"])
        out=intake(raw,p,probability_only=True,**kwargs)
        self.assertTrue(out["structural_intake_passed"])
        self.assertFalse(out["eligible_for_training"])
        self.assertTrue(verify_bundle(out["bundle"]))
        self.assertEqual(len(out["capture_bindings"]),5)
    def test_tamper_and_rehash(self):
        s,p=fixture(); del s["quote"]
        b=seal(s,p,as_of=NOW,captured_at=NOW,model_release=RELEASE,probability_only=True)
        b["market_evidence"]="VERIFIED"
        b["sha256"]=digest({k:v for k,v in b.items() if k!="sha256"})
        self.assertFalse(verify_bundle(b))
