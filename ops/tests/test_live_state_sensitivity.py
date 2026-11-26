import copy
import unittest
from ops.live_state_sensitivity import evaluate, _project

class LiveSensitivityTests(unittest.TestCase):
    def setUp(self):
        self.fixture={"gender":"men","league":"epl","home_id":"a","away_id":"b",
            "kickoff_utc":"2026-11-26T10:00:00Z","expected_identity_sealed_utc":"2026-11-26T09:00:00Z",
            "provider_event_ids":{"fotmob":"1","skysports":"2"},
            "provider_event_urls":{"fotmob":"https://www.fotmob.com/matches/a-b/1",
                                   "skysports":"https://www.skysports.com/football/a-b/live/2"}}
        self.now="2026-11-26T10:50:00Z"
        self.obs=[]
        for provider in self.fixture["provider_event_ids"]:
            self.obs.append({**{k:self.fixture[k] for k in ("gender","league","home_id","away_id","kickoff_utc")},
                "provider":provider,"source_event_id":self.fixture["provider_event_ids"][provider],
                "source_url":self.fixture["provider_event_urls"][provider],
                "captured_utc":self.now,"source_updated_utc":"2026-11-26T10:49:30Z",
                "match_status":"HALF_TIME","regulation_minute":45,"score_home":0,"score_away":1,
                "red_card_history_complete_assertion":True,
                "red_card_events":[{"source_event_id":provider+"-red","side":"HOME","minute":30,
                                    "status":"CONFIRMED_ASSERTION"}]})
    def run_case(self, obs=None, rates=(1.8,1.2)):
        return evaluate(self.fixture,self.obs if obs is None else obs,
                        as_of_utc=self.now,assumed_full_match_rates=rates)
    def test_research_only_card_stress_and_probability_conservation(self):
        r=self.run_case()
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertEqual(r["red_card_count_assertion"],[1,0])
        self.assertFalse(r["independently_authenticated"])
        self.assertEqual(r["recommendations"],[])
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for row in r["scenarios"]:
            self.assertAlmostEqual(sum(row["hypothetical_final_1x2"]),1)
        self.assertLess(r["scenarios"][2]["hypothetical_trailing_team_final_win"],
                        r["scenarios"][0]["hypothetical_trailing_team_final_win"])
    def test_missing_red_cards_not_assumed_zero(self):
        del self.obs[0]["red_card_events"]
        self.assertEqual(self.run_case()["status"],"HOLD")
        self.assertEqual(self.run_case()["scenarios"],[])
    def test_disagreement_future_card_and_duplicate_source_hold(self):
        for mutate in ("different","future","duplicate"):
            obs=copy.deepcopy(self.obs)
            if mutate=="different":obs[0]["red_card_events"][0]["side"]="AWAY"
            elif mutate=="future":obs[0]["red_card_events"][0]["minute"]=46
            else:obs[1]=copy.deepcopy(obs[0])
            self.assertEqual(self.run_case(obs)["status"],"HOLD")
    def test_stale_clock_score_and_rates_hold(self):
        obs=copy.deepcopy(self.obs)
        obs[0]["source_updated_utc"]="2026-11-26T10:48:00Z"
        self.assertEqual(self.run_case(obs)["status"],"HOLD")
        obs=copy.deepcopy(self.obs)
        obs[1]["score_home"]=1
        self.assertEqual(self.run_case(obs)["status"],"HOLD")
        self.assertEqual(self.run_case(rates=(True,1.2))["status"],"HOLD")
    def test_zero_remaining_rate_and_equal_card_control(self):
        self.assertEqual(_project(0,1,0,0)["hypothetical_final_1x2"],[0.,0.,1.])
        for o in self.obs:o["red_card_events"]=[]
        r=self.run_case()
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertEqual(r["scenarios"][0]["hypothetical_final_1x2"],r["scenarios"][2]["hypothetical_final_1x2"])

if __name__=="__main__":
    unittest.main()
