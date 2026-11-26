import unittest
from ops.v9_league_weights import blend,choose,select,compare
def row(i,y=0):
    return {"league":"en.1","season":"2024-25","date":"2024-09-17","home":str(i),"away":"B","y":y,
        "ensemble":[.4,.3,.3],"v8":[.6,.2,.2],"hybrid":[.5,.25,.25]}
class LeagueWeightTests(unittest.TestCase):
    def test_endpoints(self):
        r=row(0)
        self.assertEqual(blend(r,0),r["ensemble"])
        for a,b in zip(blend(r,1),r["v8"]):self.assertAlmostEqual(a,b)
    def test_choose(self):
        a=[row(i,i%3) for i in range(210)]
        self.assertEqual(choose(a),0.)
    def test_leakage(self):
        a=[row(i,i%3) for i in range(210)];a[-1]["season"]="2025-26"
        with self.assertRaisesRegex(ValueError,"DEVELOPMENT"):choose(a)
    def test_shrinkage(self):
        a=[row(i,i%3) for i in range(210)]
        p,w=select(a)
        self.assertEqual(w["de.1"]["final_v8_weight"],p)
        self.assertEqual(w["en.1"]["final_v8_weight"],(p+w["en.1"]["local_grid_weight"])/2)
    def test_coverage(self):
        r=row(0);r["candidate"]=r["hybrid"]
        out=compare([r],10)
        self.assertEqual(out["coverage"],.1)
        self.assertFalse(out["historical_proper_score_gate"])
    def test_small(self):
        with self.assertRaisesRegex(ValueError,"DEVELOPMENT"):choose([row(0)])
