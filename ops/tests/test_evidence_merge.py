"""Concurrency and timestamp defenses for cumulative research evidence."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evidence_merge import merge, validate


class MergeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.kickoff = datetime(2026,10,10,12,tzinfo=timezone.utc)
        self.sample = {
            "key": "fixture-1", "league": "epl", "kickoff_utc": self.kickoff.isoformat(),
            "forecast_utc": (self.kickoff - timedelta(hours=1)).isoformat(),
            "market_utc": (self.kickoff - timedelta(hours=2)).isoformat(),
            "y": 1, "p": [0.4,0.3,0.3], "m": [0.3,0.4,0.3],
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED",
        }
        self.doc = {"schema": "football-king-forward-research-1",
                    "checked_utc": (self.kickoff + timedelta(hours=3)).isoformat(),
                    "samples": [self.sample], "n":1,
                    "results_independently_verified": False,
                    "profitability_verified": False,
                    "production_recommendations": "DISABLED"}

    def test_merging_new_and_existing_samples_preserves_both(self):
        existing={**self.doc,"samples": [{**self.sample,"key":"fixture-older"}], "n":1}
        out=merge(existing,self.doc)
        self.assertEqual(out["n"],2)
        self.assertEqual(out["newly_settled"],1)

    def test_same_sample_remains_once(self):
        out=merge(self.doc,self.doc)
        self.assertEqual(out["n"],1)
        self.assertEqual(out["newly_settled"],0)

    def test_conflicting_historical_outcome_fails_closed(self):
        existing={**self.doc,"samples":[{**self.sample,"y":0}]}
        with self.assertRaisesRegex(ValueError,"CONFLICTING_RESULT"):
            merge(existing,self.doc)

    def test_market_after_prediction_is_rejected(self):
        self.sample["market_utc"]=(self.kickoff+timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(ValueError,"FORECAST_TIME_LEAKAGE"):
            validate(self.doc)

    def test_unsafe_production_label_rejected(self):
        self.doc["production_recommendations"]="ENABLED"
        with self.assertRaisesRegex(ValueError,"INVALID_EVIDENCE_SAFETY"):
            validate(self.doc)

    def test_missing_independent_result_flag_rejected(self):
        self.sample.pop("fixture_result_source_independently_verified")
        with self.assertRaisesRegex(ValueError,"UNSAFE_SETTLEMENT"):
            validate(self.doc)

    def test_bad_probabilities_rejected(self):
        self.sample["p"]=[0.8,0.8,-0.6]
        with self.assertRaisesRegex(ValueError,"UNSAFE_SETTLEMENT"):
            validate(self.doc)

    def test_missing_schema_rejected(self):
        self.doc["schema"]="legacy"
        with self.assertRaisesRegex(ValueError,"INVALID_EVIDENCE_SCHEMA"):
            validate(self.doc)


if __name__=="__main__":
    unittest.main()
