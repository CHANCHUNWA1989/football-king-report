import unittest
from datetime import date,timedelta
from live_core_two_league_elo import forecast, report, parse_bl

class TwoLeagueEloTests(unittest.TestCase):
    def train(self):
        return [((date(2020,8,1)+timedelta(days=i)).isoformat(),"A","B",i%3,1) for i in range(60)]
    def test_same_day_elo_and_team_strength_frozen(self):
        a=[("2021-08-01","A","C",0,1),("2021-08-01","C","B",1,0),("2021-08-02","A","C",0,1)]
        b=[("2021-08-01","A","C",8,0),a[1],a[2]]
        x,y=forecast(self.train(),a),forecast(self.train(),b)
        self.assertEqual(x[0][-1],y[0][-1]);self.assertEqual(x[1][-1],y[1][-1])
        self.assertNotEqual(x[2][-1],y[2][-1])
    def test_unseen_group_uses_prior_games_only(self):
        rows=[((date(2021,8,1)+timedelta(days=i)).isoformat(),"A","C",1,0) for i in range(7)]
        out=report(self.train(),rows)
        self.assertEqual(out["all"]["n"],7)
        self.assertEqual(out["unseen_team_first_five"]["n"],5)
        self.assertEqual(out["other"]["n"],2)
        self.assertIsNone(out["selected_model"])
        self.assertTrue(out["unseen_is_not_verified_promotion"])
    def test_reject_overlap_and_invalid_source_pin(self):
        with self.assertRaises(ValueError):forecast(self.train(),[self.train()[-1]])
        with self.assertRaisesRegex(ValueError,"BLOB_PIN_CHANGED"):parse_bl(b"{}","2020-21")
    def test_probability_conservation(self):
        r=forecast(self.train(),[("2021-08-01","A","C",1,0)])[0]
        for p,u in r[-1].values():
            self.assertAlmostEqual(sum(p),1)
            self.assertTrue(0<=u<=1)
