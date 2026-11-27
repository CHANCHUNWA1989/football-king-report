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

    def test_causal_experts_no_same_day_or_future_leakage(self):
        from datetime import date,timedelta
        from ops.v9_league_weights import causal_experts,EXPERTS,ANCHOR
        from ops.v6_forward_bundle import WEIGHTS
        from ops.v5_ensemble_competition import blend as mix,NAMES
        rows=[]
        for i in range(70):
            r=row(i,i%3)
            r["date"]=(date(2024,8,1)+timedelta(days=i//2)).isoformat()
            r["experts"]={k:([.6,.2,.2] if k=="v8" else [.4,.3,.3]) for k in EXPERTS}
            r["ensemble"]=mix({k:r["experts"][k] for k in NAMES},WEIGHTS)
            r["hybrid"]=[(x+y)/2 for x,y in zip(r["ensemble"],r["v8"])]
            rows.append(r)
        a=causal_experts(rows)
        changed=[dict(r) for r in rows]
        changed[-1]["y"]=(changed[-1]["y"]+1)%3
        b=causal_experts(changed)
        self.assertEqual([r["candidate"] for r in a],[r["candidate"] for r in b])
        self.assertEqual(a[0]["expert_weights"],ANCHOR)
        self.assertEqual(a[-1]["expert_weights"],a[-2]["expert_weights"])
        self.assertNotEqual(a[-1]["expert_weights"],ANCHOR)
        for r in a:
            self.assertAlmostEqual(sum(r["candidate"]),1)
            self.assertAlmostEqual(sum(r["expert_weights"].values()),1)
    def test_causal_experts_duplicate_and_mismatch(self):
        from ops.v9_league_weights import causal_experts,EXPERTS
        r=row(0)
        r["experts"]={k:[.4,.3,.3] for k in EXPERTS}
        r["experts"]["v8"]=r["v8"]
        with self.assertRaisesRegex(ValueError,"EXPERT_CASE"):
            causal_experts([r,r])
        r["experts"]["v8"]=[.3,.3,.4]
        with self.assertRaisesRegex(ValueError,"EXPERT_V8_MISMATCH"):
            causal_experts([r])
