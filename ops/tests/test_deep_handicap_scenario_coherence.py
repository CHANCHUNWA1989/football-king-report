"""Deterministic mathematical grid, not historical or prospective results."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_scenario_coherence import analyze,audit_projection,_grade
from deep_handicap_joint_score import score_distribution


class ScenarioCoherenceTests(unittest.TestCase):
    def test_quarter_oracle(self):
        self.assertEqual(_grade(2,-9),"HALF_LOSS")
        self.assertEqual(_grade(3,-11),"HALF_WIN")
        self.assertEqual(_grade(3,-12),"PUSH")
        self.assertEqual(_grade(4,-12),"FULL_WIN")
        self.assertEqual(_grade(1,-9),"FULL_LOSS")

    def test_correlated_models_not_counted_as_evidence(self):
        r=analyze(2.9,.9,"HOME",-2.25,3.25)
        self.assertEqual(r["scenario_count"],3)
        self.assertEqual(r["shared_model_family_count"],1)
        self.assertEqual(r["independent_model_evidence_count"],0)
        self.assertIsNone(r["combined_forecast"])
        self.assertFalse(r["confidence_interval_available"])
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["scenario_diagnostics"][-1]["score_total_variation_vs_baseline"],0)
        self.assertGreater(r["scenario_diagnostics"][0]["score_total_variation_vs_baseline"],0)

    def test_invalid_matrices_rejected(self):
        base=score_distribution(2.9,.9,"HOME")
        for bad in ({"bad":1},{(0,0):float("nan")},{(0,0):.7},
                    {(0,0):1.1,(1,0):-.1},{(49,0):1},{(True,0):1}):
            with self.assertRaises(ValueError):
                audit_projection(bad,"HOME",-9,13,1.0)
        original=copy.deepcopy(base)
        audit_projection(base,"HOME",-9,13,1.0)
        self.assertEqual(base,original)
        self.assertIsNone(analyze(6,1,"HOME",-2.25,3.25)["scenario_diagnostics"])

    def test_150_scenarios_and_8400_line_ladder_checks(self):
        count=checks=0
        for h in (.1,.5,1.5,3,5.5):
            for a in (.1,.5,1.5,3,5.5):
                for side in ("HOME","AWAY"):
                    r=analyze(h,a,side,-2.25,3.25)
                    self.assertEqual(r.get("scenario_count"),3,r)
                    count+=r["scenario_count"]
                    checks+=r["scenario_count"]*r["line_ladder_count_per_scenario"]
                    for d in r["scenario_diagnostics"]:
                        self.assertLessEqual(d["full_win_probability"],d["match_win_probability"]+1e-9)
        self.assertEqual(count,150)
        self.assertEqual(checks,8400)
