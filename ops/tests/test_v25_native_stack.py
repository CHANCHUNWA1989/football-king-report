import unittest
from datetime import date
from ops.v25_native_stack import portable,reference,weights,experts_for
from ops import v9_stacking_research as s,v9_league_weights as w

def row(y=0):
    return {"experts":{k:[.5,.3,.2] for k in s.EXPERTS},"y":y}

class NativeStackTests(unittest.TestCase):
    def test_portable_uniform_and_contract(self):
        m={"schema":"v25-portable-stack-v1","experts":list(s.EXPERTS),"classes":[0,1,2],
            "coef":[[0.]*16 for _ in range(3)],"intercept":[0.,0.,0.]}
        self.assertEqual(portable(m,row()),[1/3]*3)
        m["classes"]=[1,0,2]
        with self.assertRaisesRegex(ValueError,"CONTRACT"):portable(m,row())
    def test_reference_matches_causal_replay(self):
        rows=[]
        for i in range(70):
            r=row(i%3);r.update(league="de.1",date=f"2025-09-{1+i//3:02d}",home=str(i),away="B",
                v8=r["experts"]["v8"],ensemble=[.5,.3,.2])
            rows.append(r)
        a=w.causal_experts(rows)
        for r in a:
            prior=sorted([z for z in rows if z["date"]<r["date"]],key=lambda z:(z["date"],z["home"],z["away"]))
            for x,y in zip(reference(r["experts"],prior),r["candidate"]):self.assertAlmostEqual(x,y,places=12)
    def test_future_history_refused(self):
        with self.assertRaisesRegex(ValueError,"NONPRIOR"):
            experts_for([],[(date(2025,9,1),"A","B",1,0)],date(2025,9,1),"A","B",None)
    def test_missing_expert_rejected(self):
        m={"schema":"v25-portable-stack-v1","experts":list(s.EXPERTS),"classes":[0,1,2],
            "coef":[[0.]*16 for _ in range(3)],"intercept":[0.,0.,0.]}
        r=row();del r["experts"]["v8"]
        with self.assertRaises((ValueError,KeyError)):portable(m,r)
