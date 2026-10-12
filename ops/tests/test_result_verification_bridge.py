import unittest
from ops.result_verification_bridge import build_verification_status

class TestResultVerificationBridge(unittest.TestCase):
    def setUp(self):
        self.fixtures = [{"fixture_id":"fixture-1","kickoff_utc":"2026-10-10T12:00:00Z"}]
        self.a = {"fixture_id":"fixture-1","provider_id":"a","independent_group_id":"a","status":"FT","published_utc":"2026-10-10T15:00:00Z","home_goals":1,"away_goals":0}
    def test_two_independent_sources(self):
        out=build_verification_status(self.fixtures,[self.a,dict(self.a,provider_id="b",independent_group_id="b")])
        self.assertEqual(out["independently_verified_count"],1)
        self.assertEqual(out["production_recommendations"],"DISABLED")
    def test_no_sources_hold(self):
        self.assertEqual(build_verification_status(self.fixtures,[])["results"][0]["status"],"HOLD")
    def test_shared_upstream_hold(self):
        b=dict(self.a,provider_id="b")
        self.assertEqual(build_verification_status(self.fixtures,[self.a,b])["results"][0]["status"],"HOLD")
    def test_conflict_hold(self):
        b=dict(self.a,provider_id="b",independent_group_id="b",away_goals=1)
        self.assertEqual(build_verification_status(self.fixtures,[self.a,b])["results"][0]["reason"],"SOURCE_CONFLICT")
    def test_duplicate_fixture_rejected(self):
        with self.assertRaises(ValueError):
            build_verification_status(self.fixtures+self.fixtures,[])
if __name__ == "__main__":
    unittest.main()
