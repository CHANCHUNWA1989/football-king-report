import unittest
from ops.v8_ucl_confidence import features,select,report,choose,qualifies,top
def row(y=0):
    return {"season":"2024-25","date":"2024-09-17","home":"A","away":"B","y":y,
        "hybrid":[.65,.20,.15],"baseline":[.7,.15,.15],"elo":[.6,.25,.15]}
class ConfidenceTests(unittest.TestCase):
    def test_features(self):
        r=features(row(),(1.,0.,0.))
        self.assertAlmostEqual(r["tv"],.1)
        self.assertAlmostEqual(r["margin"],.45)
        self.assertTrue(r["agreement"])
    def test_disagreement(self):
        r=row();r["elo"]=[.1,.1,.8]
        f=features(r,(1.,0.,0.))
        self.assertFalse(f["agreement"])
        self.assertEqual(select([f],(.5,0.,1.,True)),[])
    def test_empty(self):
        self.assertIsNone(report([],144)["accuracy"])
        self.assertFalse(qualifies(report([],144)))
    def test_rule_minimum(self):
        r=features(row(),(1.,0.,0.))
        self.assertIsNone(choose([r]*99))
        self.assertIsNotNone(choose([r]*100))
    def test_assessment_rejected(self):
        r=features(row(),(1.,0.,0.));r["season"]="2025-26"
        with self.assertRaisesRegex(ValueError,"LEAKAGE"):choose([r])
    def test_coverage(self):
        r=features(row(),(1.,0.,0.))
        self.assertFalse(qualifies(report([r]*100,500)))
