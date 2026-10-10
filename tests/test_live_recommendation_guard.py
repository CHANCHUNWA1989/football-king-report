import unittest
from datetime import datetime, timedelta, timezone
from ops.live_recommendation_guard import evaluate

NOW=datetime(2026,10,10,15,40,tzinfo=timezone.utc)
KICK=(NOW-timedelta(hours=1)).isoformat()
def obs(provider,score=(2,0),state="HALF_TIME",age=10):
    return {"provider":provider,"state":state,"home_goals":score[0],
            "away_goals":score[1],
            "observed_utc":(NOW-timedelta(seconds=age)).isoformat()}

class LiveGuardTests(unittest.TestCase):
    def test_two_sources_confirm_2_0_but_never_recommend(self):
        r=evaluate(KICK,[obs("a"),obs("b")],now=NOW)
        self.assertEqual(r["verified_live_score"]["home"],2)
        self.assertEqual(r["verified_live_score"]["away"],0)
        self.assertFalse(r["in_play_betting_recommendation_allowed"])
        self.assertFalse(r["pre_match_probabilities_reusable_in_play"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_conflicting_sources_hold(self):
        r=evaluate(KICK,[obs("a"),obs("b",(1,0))],now=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertIsNone(r["verified_live_score"])
    def test_stale_and_one_provider_hold(self):
        for observations in ([obs("a")],[obs("a",age=120),obs("b")],
                             [obs("a"),obs("a")],[]):
            with self.subTest(observations=observations):
                self.assertEqual(evaluate(KICK,observations,now=NOW)["status"],"HOLD")
    def test_not_started_cannot_claim_live(self):
        r=evaluate((NOW+timedelta(hours=1)).isoformat(),[obs("a"),obs("b")],now=NOW)
        self.assertIsNone(r["verified_live_score"])
        self.assertFalse(r["betting_recommendation_allowed"])
    def test_full_time_no_betting(self):
        r=evaluate(KICK,[obs("a",(5,1),"FULL_TIME"),obs("b",(5,1),"FULL_TIME")],now=NOW)
        self.assertEqual(r["status"],"FINAL_CONFIRMED")
        self.assertFalse(r["betting_recommendation_allowed"])
    def test_fake_future_quote_rejected(self):
        future=obs("b",age=-50)
        self.assertEqual(evaluate(KICK,[obs("a"),future],now=NOW)["status"],"HOLD")

if __name__=="__main__":
    unittest.main()
