import unittest
from ops.v26_nonlinear_meta import features,blend,select
from ops import v9_stacking_research as s

def row(i=0):
    return {"experts":{k:[.5,.3,.2] for k in s.EXPERTS},"candidate":[.5,.3,.2],"y":i%3,"season":s.CAL}

class NonlinearMetaTests(unittest.TestCase):
    def test_features_label_independent(self):
        r=row();a=features(r);r["y"]=2
        self.assertEqual(a,features(r));self.assertEqual(len(a),23)
    def test_exact_anchor_fallback(self):
        self.assertEqual(blend([.5,.3,.2],[.1,.1,.8],1.,0.),[.5,.3,.2])
        self.assertAlmostEqual(sum(blend([.5,.3,.2],[.1,.1,.8],1.,.25)),1.)
    def test_calibration_scope(self):
        rows=[row(i) for i in range(210)];p=[[1/3]*3]*len(rows)
        self.assertEqual(select(rows,p,p),(1.,0.))
        rows[-1]["season"]=s.TEST
        with self.assertRaisesRegex(ValueError,"CAL_SCOPE"):select(rows,p,p)
