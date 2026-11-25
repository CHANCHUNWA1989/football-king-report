import unittest
from datetime import date,timedelta
from ops.v9_historical_elo import replay
from ops.v5_dynamic_elo import replay as original
from ops.v9_expanded_ml import average,training_partition
from ops.v5_ml_benchmark import BACKENDS
def doc(y):
    d=date(y,8,1)
    # unique directed pairs, enough prior matches for nonempty predictions
    teams=[str(i) for i in range(10)]
    return {"matches":[{"date":(d+timedelta(days=i)).isoformat(),"team1":h,"team2":a,"score":[i%3,1]} for i,(h,a) in enumerate((h,a) for h in teams for a in teams if h!=a)]}
class HistoricalMLTests(unittest.TestCase):
    def test_old_dates(self):
        self.assertTrue(replay(doc(2022),"2022-23"))
    def test_equivalence(self):
        d=doc(2024)
        self.assertTrue(original(d))
        self.assertEqual(original(d),replay(d,"2024-25"))
    def test_wrong_season(self):
        with self.assertRaisesRegex(ValueError,"OUTSIDE_SEASON"):replay(doc(2022),"2024-25")
    def test_average(self):
        p={k:[[.5,.3,.2]] for k in BACKENDS}
        for a,b in zip(average(p,0),[.5,.3,.2]):self.assertAlmostEqual(a,b)
    def test_insufficient_train(self):
        with self.assertRaisesRegex(ValueError,"INSUFFICIENT_TRAIN"):training_partition({("2025-26","en.1"):[(date(2025,8,1),"A","B",1,0)]},"en.1")
