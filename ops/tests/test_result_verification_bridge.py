import unittest
from ops.result_consensus_gate import verify_result

class TestResultVerificationBridge(unittest.TestCase):
    def setUp(self):
        self.fixtures = [{"fixture_id":"fixture-1","kickoff_utc":"2026-10-10T12:00:00Z"}]
        self.a = {"fixture_id":"fixture-1","provider_id":"a","independent_group_id":"a","status":"FT","published_utc":"2026-10-10T15:00:00Z","home_goals":1,"away_goals":0}
    def test_two_independent_sources(self):
        out=verify_result("fixture-1", self.fixtures[0]["kickoff_utc"], [self.a,dict(self.a,provider_id="b",independent_group_id="b")])
        self.assertEqual(out["status"],"VERIFIED")

    def test_no_sources_hold(self):
        self.assertEqual(verify_result("fixture-1", self.fixtures[0]["kickoff_utc"], [])["status"],"HOLD")
    def test_shared_upstream_hold(self):
        b=dict(self.a,provider_id="b")
        self.assertEqual(verify_result("fixture-1", self.fixtures[0]["kickoff_utc"], [self.a,b])["status"],"HOLD")
    def test_conflict_hold(self):
        b=dict(self.a,provider_id="b",independent_group_id="b",away_goals=1)
        self.assertEqual(verify_result("fixture-1", self.fixtures[0]["kickoff_utc"], [self.a,b])["reason"],"SOURCE_CONFLICT")
    def test_wrong_fixture_rejected(self):
        self.assertEqual(verify_result("another-fixture", self.fixtures[0]["kickoff_utc"], [self.a])["status"], "HOLD")
if __name__ == "__main__":
    unittest.main()
