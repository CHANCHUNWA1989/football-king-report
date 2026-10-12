import unittest
from ops.result_consensus_gate import verify_result

class TestResultConsensusGate(unittest.TestCase):
    def setUp(self):
        self.kickoff = "2026-10-10T12:00:00Z"
        self.a = {"fixture_id":"match-1","provider_id":"provider-a","independent_group_id":"upstream-a","status":"FT","published_utc":"2026-10-10T15:00:00Z","home_goals":2,"away_goals":1}
    def test_two_independent_agree(self):
        b = dict(self.a, provider_id="provider-b", independent_group_id="upstream-b")
        self.assertEqual(verify_result("match-1",self.kickoff,[self.a,b])["status"],"VERIFIED")
    def test_one_source_is_hold(self):
        self.assertEqual(verify_result("match-1",self.kickoff,[self.a])["status"],"HOLD")
    def test_conflict_is_hold(self):
        b = dict(self.a, provider_id="provider-b",independent_group_id="upstream-b",away_goals=0)
        self.assertEqual(verify_result("match-1",self.kickoff,[self.a,b])["reason"],"SOURCE_CONFLICT")
    def test_pre_kickoff_not_accepted(self):
        b = dict(self.a, provider_id="provider-b",independent_group_id="upstream-b",published_utc="2026-10-10T11:00:00Z")
        self.assertEqual(verify_result("match-1",self.kickoff,[self.a,b])["status"],"HOLD")
    def test_duplicate_provider_not_independent(self):
        self.assertEqual(verify_result("match-1",self.kickoff,[self.a,self.a])["status"],"HOLD")
    def test_shared_underlying_feed_is_not_independent(self):
        a = dict(self.a, independent_group_id="same-feed")
        b = dict(self.a, provider_id="provider-b", independent_group_id="same-feed")
        self.assertEqual(verify_result("match-1", self.kickoff, [a, b])["status"], "HOLD")
    def test_naive_time_rejected(self):
        self.assertEqual(verify_result("match-1","2026-10-10T12:00:00",[self.a])["reason"],"INVALID_INPUT")

    def test_missing_group_is_hold(self):
        a = dict(self.a)
        a.pop("independent_group_id")
        b = dict(a, provider_id="provider-b")
        self.assertEqual(verify_result("match-1", self.kickoff, [a, b])["status"], "HOLD")
    def test_non_dict_observation_is_ignored(self):
        self.assertEqual(verify_result("match-1", self.kickoff, [None, self.a])["status"], "HOLD")

if __name__ == "__main__":
    unittest.main()
