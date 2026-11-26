import unittest
import copy
import hashlib
import json
from unittest.mock import patch
from test_production_gate import research_evidence
from production_gate import gate
from qualification_rehearsal import rehearsal, verify

class QualificationRehearsalTests(unittest.TestCase):
    def test_invalid_confidence_intervals_never_pass(self):
        center={"production_recommendations":"DISABLED"}
        evidence=research_evidence()
        for ci in ([.2,.1],[.1,float("inf")],[float("nan"),.1],[True,.2]):
            result=gate(center,evidence,{"production_recommendations":"DISABLED","measurements":{"difference_block_bootstrap_95pct_ci":ci}})
            self.assertFalse(result["conditions"]["positive_week_block_bootstrap_lower_ci_against_market"])
    def test_bool_count_rejected(self):
        evidence=research_evidence()
        evidence["samples"]=evidence["samples"][:1]
        evidence["n"]=True
        with self.assertRaises(ValueError):gate({"production_recommendations":"DISABLED"},evidence,{"production_recommendations":"DISABLED"})
    def test_pin_and_full_pipeline_without_challengers(self):
        doc=research_evidence()
        raw=json.dumps(doc).encode()
        pin=hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()
        with self.assertRaises(ValueError):verify(raw)
        with patch("qualification_rehearsal.PIN",pin):
            out=rehearsal(raw)
        self.assertEqual(out["recorded_research_samples"],300)
        self.assertEqual(out["fourway_cases"],0)
        self.assertEqual(out["authenticated_forward_samples"],0)
        self.assertTrue(out["mobile_outputs_verified"])
        self.assertFalse(out["actual_daily_run"])
        self.assertEqual(out["remaining_authenticated_samples"],300)
