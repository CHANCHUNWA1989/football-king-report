import unittest
from ops.evidence_coverage import evidence_coverage

def record(i):
    return dict(event_id=f"synthetic-{i}",competition="Synthetic",kickoff_at="2026-11-06T20:00:00+08:00",
                captured_at="2026-11-06T19:45:00+08:00",forecast_created_at="2026-11-06T19:30:00+08:00",
                bookmaker="TEST_ONLY",source_url="https://example.invalid/fixture",
                market="total",side="under",line="2.5",odds="1.87",home_goals=0,away_goals=0,
                model_version="synthetic",score_probabilities={"0-0":"0.6","1-1":"0.4"})

class EvidenceCoverageTests(unittest.TestCase):
    def test_coverage_not_certification(self):
        x=evidence_coverage([record(1),record(2)])
        self.assertEqual(x["snapshot_count"],2)
        self.assertEqual(x["unique_event_count"],2)
        self.assertFalse(x["source_authenticity_verified"])
        self.assertFalse(x["out_of_sample_verified"])
        self.assertFalse(x["positive_ev_verified"])
        self.assertFalse(x["production_recommendation_allowed"])
    def test_empty_rejected(self):
        with self.assertRaises(ValueError): evidence_coverage([])
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError): evidence_coverage([record(1),record(1)])
    def test_stale_rejected(self):
        x=record(1);x["captured_at"]="2026-11-06T18:00:00+08:00"
        with self.assertRaises(ValueError): evidence_coverage([x])
    def test_provider_coverage(self):
        x=record(1);y=record(2);y["bookmaker"]="SECOND_TEST_ONLY"
        self.assertEqual(len(evidence_coverage([x,y])["bookmakers"]),2)

if __name__=="__main__":
    unittest.main()
