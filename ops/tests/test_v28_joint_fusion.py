import unittest
from ops.v28_joint_fusion import fuse,select,RULES,NAMES
def row(i=0):
    return {"season":"2024-25","date":"2025-02-01","y":i%3,
            "stack":[1/3]*3,**{k:[1/3]*3 for k in NAMES}}
class JointFusionTests(unittest.TestCase):
    def test_grid_and_mass(self):
        self.assertTrue(all(sum(q)<=3 for q,t in RULES))
        r=row();r["bayes"]=[.1,.1,.8]
        for rule in RULES:self.assertAlmostEqual(sum(fuse(r,rule)),1.)
        self.assertEqual(fuse(r,((0,0,0),1.)),r["stack"])
        with self.assertRaisesRegex(ValueError,"FUSION_RULE"):fuse(r,((2,2,2),1.))
    def test_zero_weight_fallback(self):
        self.assertEqual(select([row(i) for i in range(210)]),((0,0,0),1.))
    def test_assessment_excluded(self):
        rows=[row(i) for i in range(210)];rows[-1]["date"]="2025-07-01"
        with self.assertRaisesRegex(ValueError,"CAL_SCOPE"):select(rows)
