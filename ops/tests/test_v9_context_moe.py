import unittest
from ops.v9_context_moe import context,fit_gate,infer,calibrate,mix,NAMES,DIM

def row(i,season="2022-23",y=0):
    return {"league":"en.1","season":season,"date":season[:4]+"-09-01",
            "home":str(i),"away":"B","y":y,
            "experts":{k:[.5,.3,.2] for k in NAMES[:-1]},
            "bayes":[.3,.4,.3],"candidate":[.5,.3,.2]}

class ContextMoETests(unittest.TestCase):
    def test_context_excludes_outcome(self):
        r=row(0);a=context(r);r["y"]=2
        self.assertEqual(a,context(r));self.assertEqual(len(a),DIM)
        r["league"]="de.1";self.assertNotEqual(a,context(r))
    def test_fit_and_normalized_inference(self):
        try:import numpy,scipy
        except ImportError:self.skipTest("optional ML dependencies")
        rows=[row(i,y=i%3) for i in range(210)]
        theta=fit_gate(rows)
        a,w=infer(rows[:2],theta)
        for p,q in zip(a,w):
            self.assertAlmostEqual(sum(p),1)
            self.assertAlmostEqual(sum(q),1)
        rows[0]["season"]="2025-26"
        with self.assertRaisesRegex(ValueError,"MOE_TRAIN_SCOPE"):fit_gate(rows)
    def test_calibration_scope_and_reference_endpoint(self):
        rows=[row(i,"2024-25",i%3) for i in range(210)]
        a=[[.5,.3,.2]]*len(rows);b=[[.3,.4,.3]]*len(rows)
        self.assertIn(calibrate(rows,a,b),(0.,.25,.5,.75,1.))
        self.assertEqual(mix(a[0],b[0],0.),a[0])
        rows[-1]["season"]="2025-26"
        with self.assertRaisesRegex(ValueError,"MOE_CAL_SCOPE"):calibrate(rows,a,b)
