"""Synthetic tests for the coefficient research gate and fixed grid."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_vnext_native_cohort import fixture, AS_OF
from vnext_native_coefficients import evaluate_coefficients, _select, _metrics, _prob, GRID, REFERENCE

class CoefficientTests(unittest.TestCase):
    def test_insufficient_data_never_fits(self):
        out=evaluate_coefficients([fixture()],split_utc="2026-11-03T21:55:00Z",as_of_utc=AS_OF)
        self.assertEqual(out["reason"],"INSUFFICIENT_RESEARCH_COVERAGE")
        self.assertEqual(out["train_n"],1)
        self.assertIsNone(out["candidate_parameters"])
        self.assertFalse(out["weight_updates_applied"])
        self.assertEqual(out["verified_forward_sample_credit"],0)
        self.assertEqual(out["production_recommendations"],"DISABLED")
    def test_label_crossing_cutoff_and_duplicates(self):
        c=fixture()
        out=evaluate_coefficients([c],split_utc="2026-11-03T21:40:00Z",as_of_utc=AS_OF)
        self.assertEqual(out["reason"],"TRAINING_LABEL_AFTER_SPLIT")
        out=evaluate_coefficients([c,copy.deepcopy(c)],split_utc="2026-11-03T21:55:00Z",as_of_utc=AS_OF)
        self.assertEqual(out["reason"],"DUPLICATE_CALIBRATION_FIXTURE")
    def test_grid_determinism_and_normalization(self):
        row=dict(score=[1,1],red_cards=[1,0],minute=50,rates=(1.6,1.4),outcome="AWAY")
        train=[row]*10
        candidate=_select(train)
        self.assertIn(candidate,GRID)
        self.assertEqual(candidate,_select(list(reversed(train))))
        for pair in GRID:
            self.assertAlmostEqual(sum(_prob(row,pair).values()),1)
            m=_metrics(train,pair)
            self.assertTrue(0<=m["brier"]<=2)
            self.assertTrue(m["log_loss"]>=0)
        self.assertIn(REFERENCE,GRID)
    def test_invalid_series_not_used(self):
        c=fixture()
        c["cuts"][1]["snapshot"]["quote"]["decimal_price"]=2.1
        out=evaluate_coefficients([c],split_utc="2026-11-03T21:55:00Z",as_of_utc=AS_OF)
        self.assertEqual(out["reason"],"CALIBRATION_CASE_REJECTED")
        self.assertNotIn("assessment_metrics",out)
