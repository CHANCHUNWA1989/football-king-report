"""Synthetic cross-market conservation and settlement regression tests."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_joint_score import project, score_distribution
from deep_handicap_diagnostics import _joint
from asian_handicap_research import probabilities, TYPES


class JointScoreTests(unittest.TestCase):
    def test_market_mass_and_existing_baseline(self):
        for h,a in ((2.95,1.17),(.1,.1),(5.5,5.5)):
            for side in ("HOME","AWAY"):
                p=project(h,a,side,-2.25,3.25)
                for key in ("one_x_two","handicap","over","under"):
                    self.assertAlmostEqual(sum(p[key].values()),1,places=9)
                prior=probabilities(h,a,side,-2.25)["outcome_probabilities"]
                for g in TYPES:
                    self.assertAlmostEqual(prior[g],p["handicap"][g],places=6)
                self.assertAlmostEqual(sum(x["probability"] for x in p["top_scores"])+p["other_score_probability"],1)
                self.assertEqual(p["status"],"HOLD")
                self.assertFalse(p["qualifies_for_betting"])

    def test_mirrored_conditional_score_pmf(self):
        x=score_distribution(2.9,.9,"HOME",.85)
        y=score_distribution(.9,2.9,"AWAY",.85)
        for (h,a),p in x.items():
            self.assertAlmostEqual(p,y[a,h],places=12)
        self.assertAlmostEqual(sum(x.values()),1,places=9)

    def test_joint_marginals_and_conditional_dhe_consistency(self):
        for pace in (.65,.85,1.0):
            p=project(2.95,1.17,"HOME",-2.25,4,pace=pace)
            d=_joint(2.95,1.17,"HOME",-2.25,pace)
            for g in TYPES:
                self.assertAlmostEqual(p["handicap"][g],d["grades"][g],places=10)
                self.assertAlmostEqual(sum(p["handicap_and_over_joint"][g].values()),p["handicap"][g],places=10)
                self.assertAlmostEqual(sum(p["handicap_and_over_joint"][k][g] for k in TYPES),p["over"][g],places=10)
            self.assertAlmostEqual(p["over"]["FULL_WIN"],p["under"]["FULL_LOSS"])
            self.assertAlmostEqual(p["over"]["PUSH"],p["under"]["PUSH"])
            self.assertEqual(p["over"]["HALF_WIN"],0)
            self.assertEqual(p["over"]["HALF_LOSS"],0)

    def test_total_quarter_push_and_half_grades(self):
        score=score_distribution(2.9,.9,"HOME")
        exact3=sum(p for (h,a),p in score.items() if h+a==3)
        for line,key in ((3,"PUSH"),(3.25,"HALF_LOSS"),(2.75,"HALF_WIN")):
            p=project(2.9,.9,"HOME",-2.25,line)
            self.assertAlmostEqual(p["over"][key],exact3,places=10)
        p=project(2.9,.9,"HOME",-2.25,10)
        self.assertAlmostEqual(sum(p["over"].values()),1)

    def test_invalid_inputs_fail_closed(self):
        for args in ((True,1,"HOME",-2,3),(1,1,"HOME",-1,3),(1,1,"BAD",-2,3),
                     (1,1,"HOME",-2,3.1),(1,1,"HOME",-2,True),(1,1,"HOME",-2,11)):
            with self.assertRaises(ValueError):
                project(*args)
        for pace in (True,.8,float("nan")):
            with self.assertRaises(ValueError):
                project(1,1,"HOME",-2,3,pace=pace)
