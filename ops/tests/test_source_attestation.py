import unittest
from ops.source_attestation import review_source_attestation

def row():
    return dict(event_id="synthetic-1",competition="Synthetic",kickoff_at="2026-11-06T20:00:00+08:00",
                captured_at="2026-11-06T19:45:00+08:00",forecast_created_at="2026-11-06T19:30:00+08:00",
                bookmaker="TEST_ONLY",source_url="https://example.invalid/fixture",
                market="total",side="under",line="2.5",odds="1.87",home_goals=0,away_goals=0,
                model_version="synthetic",score_probabilities={"0-0":"0.6","1-1":"0.4"})
def attestation():
    return dict(provider_name="TEST_ONLY",license_reference="test-ref",
                reviewer="test-reviewer",reviewed_at="2026-11-06T21:00:00+08:00",
                source_domain="example.invalid",data_access_scope="synthetic",
                forecast_lineage_reference="synthetic-model")

class AttestationTests(unittest.TestCase):
    def test_complete_still_hold(self):
        result=review_source_attestation([row()],attestation())
        self.assertTrue(result["attestation_fields_complete"])
        self.assertEqual(result["decision"],"HOLD")
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["production_recommendation_allowed"])
    def test_missing_fields_flagged(self):
        result=review_source_attestation([row()],{})
        self.assertFalse(result["attestation_fields_complete"])
        self.assertTrue(result["review_flags"])
    def test_mismatched_domain(self):
        a=attestation();a["source_domain"]="different.example"
        self.assertIn("source domain mismatch",review_source_attestation([row()],a)["review_flags"])
    def test_naive_review_time(self):
        a=attestation();a["reviewed_at"]="2026-11-06T21:00:00"
        self.assertIn("invalid review timestamp",review_source_attestation([row()],a)["review_flags"])
    def test_invalid_records_rejected(self):
        x=row();x["captured_at"]=x["kickoff_at"]
        with self.assertRaises(ValueError): review_source_attestation([x],attestation())
    def test_invalid_attestations_rejected(self):
        with self.assertRaises(ValueError): review_source_attestation([row()],None)

if __name__=="__main__":
    unittest.main()
