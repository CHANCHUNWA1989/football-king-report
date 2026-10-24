import unittest
from ops.recommendation_readiness import audit, grounded_progress, REQUIRED

class ReadinessTests(unittest.TestCase):
    def test_empty_is_hold(self):
        r = audit({})
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertEqual(set(r["missing_or_unverified"]), set(REQUIRED))
    def test_grounded_progress_dedupes_and_refuses_fake_results(self):
        sample = {"key": "fixture-one", "league": "epl",
                  "kickoff_utc": "2026-10-09T11:00:00+00:00",
                  "fixture_result_source_independently_verified": False}
        r = grounded_progress(
            {"samples": [sample, dict(sample)]},
            {"checks": [{"key": "model_promotion_safety", "state": "PASS"},
                        {"key": "out_of_sample_calibration", "state": "HOLD"}]},
            {"collector_status": "CONNECTED", "quotes": [{"market": "h2h"}]},
            {"status": "RESEARCH_ONLY", "event_count": 117})
        self.assertEqual(r["settled_cases_in_archive"], 1)
        self.assertEqual(r["additional_settled_cases_needed"], 299)
        self.assertEqual(r["independently_verified_result_cases"], 0)
        self.assertEqual(r["seven_quality_gates_passed"], 1)
        self.assertEqual(r["private_quotes_collected"], 1)
        self.assertFalse(r["market_consensus_is_executable_quote"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_duplicate_and_unknown_gate_claims_cannot_inflate_progress(self):
        for states in (("PASS", "HOLD"), ("HOLD", "PASS"), ("PASS", "PASS")):
            with self.subTest(states=states):
                checks = [{"key": "model_promotion_safety", "state": s} for s in states]
                checks += [{"key": "invented_gate", "state": "PASS"}, {"state": "PASS"}]
                result = grounded_progress({}, {"checks": checks}, {}, {})
                self.assertEqual(result["seven_quality_gates_passed"], 0)
                self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_forged_booleans_cannot_certify(self):
        r = audit({k: True for k in REQUIRED})
        self.assertEqual(r["status"], "HOLD")
    def test_metadata_alone_cannot_enable_recommendations(self):
        claimed = {k: {"passed": True, "artifact_sha256": "a"*64, "reviewed_by": "someone"} for k in REQUIRED}
        result = audit(claimed)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertTrue(all(not x["passed"] for x in result["checks"].values()))
        self.assertTrue(all(x["metadata_present"] for x in result["checks"].values()))

if __name__ == "__main__":
    unittest.main()
