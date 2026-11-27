"""Synthetic walk-forward tests; no real fixture evidence."""
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_vnext_native_cohort import fixture, AS_OF
from vnext_native_walkforward import _walk,evaluate_walkforward

BASE=datetime(2026,1,1,tzinfo=timezone.utc)

def rows():
    # Distinct synthetic kickoffs; three outcome classes and affected states.
    return [dict(kickoff=BASE+timedelta(days=i),
                 receipt=BASE+timedelta(days=i,hours=3),
                 score=[1,0],red_cards=[1,0],minute=50,rates=(1.6,1.4),
                 outcome=("HOME","DRAW","AWAY")[i%3]) for i in range(120)]

class WalkTests(unittest.TestCase):
    def test_positive_two_disjoint_folds(self):
        bounds=[BASE+timedelta(days=i) for i in (60,90,120)]
        folds,reason=_walk(rows(),bounds)
        self.assertIsNone(reason)
        self.assertEqual([f["train_n"] for f in folds],[60,90])
        self.assertEqual([f["assessment_n"] for f in folds],[30,30])
        self.assertTrue(all(f["candidate"]["n"]==f["reference"]["n"] for f in folds))
    def test_late_label_not_used_in_train(self):
        bounds=[BASE+timedelta(days=i) for i in (60,90,120)]
        r=rows()
        r[0]["receipt"]=bounds[0]
        folds,reason=_walk(r,bounds)
        self.assertIsNone(folds)
        self.assertEqual(reason,"INSUFFICIENT_FOLD_COVERAGE")
    def test_assessment_label_crossing_window(self):
        bounds=[BASE+timedelta(days=i) for i in (60,90,120)]
        r=rows();r[89]["receipt"]=bounds[1]
        self.assertEqual(_walk(r,bounds),(None,"ASSESSMENT_LABEL_AFTER_WINDOW"))
    def test_integration_insufficient_and_bad_boundaries(self):
        bounds=["2026-11-03T21:55:00Z","2026-11-03T21:57:00Z",AS_OF]
        out=evaluate_walkforward([fixture()],boundaries_utc=bounds,as_of_utc=AS_OF)
        self.assertEqual(out["reason"],"INSUFFICIENT_FOLD_COVERAGE")
        self.assertNotIn("folds",out)
        self.assertEqual(out["verified_forward_sample_credit"],0)
        out=evaluate_walkforward([fixture()],boundaries_utc=bounds[::-1],as_of_utc=AS_OF)
        self.assertEqual(out["reason"],"INVALID_WALKFORWARD_BOUNDARIES")
