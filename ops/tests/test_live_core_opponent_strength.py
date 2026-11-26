import unittest
from datetime import date,timedelta
from live_core_opponent_strength import forecasts,report,factors,adjusted,parse
class OpponentStrengthTests(unittest.TestCase):
    def train(self):
        return [((date(2023,8,1)+timedelta(days=i)).isoformat(),"A","B",i%3,1) for i in range(60)]
    def test_same_date_frozen(self):
        a=[("2024-08-01","A","C",0,1),("2024-08-01","B","C",1,0),("2024-08-02","A","C",0,1)]
        b=[("2024-08-01","A","C",8,0),a[1],a[2]]
        x,y=forecasts(self.train(),a),forecasts(self.train(),b)
        self.assertEqual(x[0][5:],y[0][5:]);self.assertEqual(x[1][5:],y[1][5:])
        self.assertNotEqual(x[2][-1],y[2][-1])
    def test_opponent_exposure_changes_strength(self):
        self.assertGreater(factors([5,2,0,0])[0],factors([5,8,0,0])[0])
        self.assertEqual(adjusted([0]*4,[0]*4,1.5,1.2),(1.5,1.2))
    def test_partition_and_probability(self):
        r=report(self.train(),[("2024-08-01","A","B",0,1)])
        self.assertEqual(sum(v["n"] for v in r["baseline_pre_match_bands"].values()),1)
        self.assertIsNone(r["selected_model"])
        for p,u in forecasts(self.train(),[("2024-08-01","A","B",0,1)])[0][-1].values():
            self.assertAlmostEqual(sum(p),1);self.assertTrue(0<=u<=1)
    def test_reject_overlap_and_pin(self):
        with self.assertRaises(ValueError):forecasts(self.train(),[self.train()[-1]])
        with self.assertRaisesRegex(ValueError,"BLOB_PIN_CHANGED"):parse(b"{}","EPL")
