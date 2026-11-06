import unittest
from ops.snapshot_validation import validate_snapshot, validate_dataset

def good():
    return dict(event_id="synthetic-001",competition="Synthetic",kickoff_at="2026-11-06T20:00:00+08:00",
                captured_at="2026-11-06T19:45:00+08:00",forecast_created_at="2026-11-06T19:30:00+08:00",
                bookmaker="TEST_ONLY",source_url="https://example.invalid/fixture",
                market="total",side="under",line="2.5",odds="1.87",home_goals=0,away_goals=0,
                model_version="synthetic",score_probabilities={"0-0":"0.6","1-1":"0.4"})

class SnapshotTests(unittest.TestCase):
    def test_valid_is_unverified(self):
        r=validate_snapshot(good())
        self.assertEqual(r["evidence_status"],"UNVERIFIED")
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["production_recommendation_allowed"])
    def test_missing_source(self):
        x=good();del x["source_url"]
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_postkickoff_quote(self):
        x=good();x["captured_at"]=x["kickoff_at"]
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_future_forecast(self):
        x=good();x["forecast_created_at"]=x["kickoff_at"]
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_stale_quote(self):
        x=good();x["captured_at"]="2026-11-06T18:00:00+08:00"
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_invalid_probabilities(self):
        x=good();x["score_probabilities"]={"0-0":"0.8"}
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_negative_probabilities(self):
        x=good();x["score_probabilities"]={"0-0":"1.1","1-1":"-0.1"}
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_invalid_market(self):
        x=good();x["market"]="moneyline"
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_invalid_line(self):
        x=good();x["line"]="2.3"
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_duplicate(self):
        with self.assertRaises(ValueError): validate_dataset([good(),good()])
    def test_dataset_one(self):
        self.assertEqual(len(validate_dataset([good()])),1)
    def test_naive_datetime(self):
        x=good();x["captured_at"]="2026-11-06T19:45:00"
        with self.assertRaises(ValueError): validate_snapshot(x)

if __name__=="__main__":
    unittest.main()
