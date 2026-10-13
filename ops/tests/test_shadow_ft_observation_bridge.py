import unittest
from shadow_ft_observation_bridge import observations
S={"fixture_id":"f1","league":"bundesliga","home":"A","away":"B","kickoff_utc":"2026-10-12T12:00:00Z"}
R={"league":"bundesliga","home":"A","away":"B","kickoff_utc":"2026-10-12T12:00:00Z","status":"FINISHED","score_ft":[2,1]}
class FTBridgeTests(unittest.TestCase):
    def test_exact_match_single_provider(self):
        x=observations([S],[R],"source-a","group-a","2026-10-12T15:00:00Z")
        self.assertEqual(len(x),1)
        self.assertEqual(x[0]["home_goals"],2)
    def test_wrong_team_excluded(self):
        self.assertEqual(observations([S],[dict(R,away="C")],"a","g","2026-10-12T15:00:00Z"),[])
    def test_ambiguous_duplicate_excluded(self):
        self.assertEqual(observations([S],[R,R],"a","g","2026-10-12T15:00:00Z"),[])
    def test_pre_kickoff_publication_excluded(self):
        self.assertEqual(observations([S],[R],"a","g","2026-10-12T11:00:00Z"),[])
if __name__=="__main__":unittest.main()
