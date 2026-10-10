import unittest
from ops.recommendation_readiness import audit, REQUIRED

class ReadinessTests(unittest.TestCase):
    def test_empty_is_hold(self):
        r = audit({})
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertEqual(set(r["missing_or_unverified"]), set(REQUIRED))
    def test_forged_booleans_cannot_certify(self):
        r = audit({k: True for k in REQUIRED})
        self.assertEqual(r["status"], "HOLD")
    def test_metadata_alone_cannot_enable_recommendations(self):
        claimed = {k: {"passed": True, "artifact_sha256": "a"*64, "reviewed_by": "someone"} for k in REQUIRED}
        self.assertEqual(audit(claimed)["production_recommendations"], "DISABLED")

if __name__ == "__main__":
    unittest.main()
