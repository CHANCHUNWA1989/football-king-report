import unittest
from ops.v6_league_calibration import evaluate,fit,IDENTITY
from ops.v5_ensemble_competition import NAMES

def cases():
    return [{"league":league,"date":"2025-12-01" if i<80 else "2026-01-02",
             "home":str(i),"away":"a","y":i%3,"base":[.6,.2,.2],"p":{k:[.6,.2,.2] for k in NAMES}}
             for league in ("a","b") for i in range(160)]
class LeagueCalibrationTests(unittest.TestCase):
    def test_sparse_identity(self):
        self.assertEqual(fit(cases()[:59]),IDENTITY)
    def test_future_rejected(self):
        with self.assertRaisesRegex(ValueError,"LEAKAGE"):fit(cases())
    def test_holdout_invariance(self):
        a=cases();b=cases()
        for r in b:
            if r["date"]>="2026-01-01":r["y"]=(r["y"]+1)%3
        x,y=evaluate(a),evaluate(b)
        for k in ("a","b"):self.assertEqual(x["per_league"][k]["params"],y["per_league"][k]["params"])
        self.assertFalse(x["automatic_promotion"])
    def test_league_isolation(self):
        a=cases();b=cases()
        for r in b:
            if r["league"]=="b" and r["date"]<"2026-01-01":r["y"]=0
        x,y=evaluate(a),evaluate(b)
        self.assertEqual(x["per_league"]["a"]["params"],y["per_league"]["a"]["params"])
        self.assertEqual(y["per_league"]["b"]["params"],list(IDENTITY))
    def test_duplicate(self):
        a=cases()
        with self.assertRaises(ValueError):evaluate(a+[a[0]])
