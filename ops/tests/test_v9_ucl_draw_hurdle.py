import unittest
from ops.v9_ucl_draw_hurdle import predict,fit,diagnostic

def row(i):
    return {"date":"2024-09-01","season":"2024-25","y":i%3,
            "reference":[.5,.2,.3],"home_rate":1.5,"away_rate":1.2}
class DrawHurdleTests(unittest.TestCase):
    def test_identity_normalization_and_direction(self):
        r=row(0)
        self.assertEqual(predict(r,(0.,0.,0.,1.)),r["reference"])
        p=predict(r,(.3,0.,0.,1.))
        self.assertGreater(p[1],r["reference"][1])
        self.assertAlmostEqual(sum(p),1)
        self.assertAlmostEqual(p[0]/p[2],.5/.3)
        q=predict(r,(0.,0.,0.,1.2))
        self.assertLess(q[0]/q[2],.5/.3)
    def test_no_label_feature(self):
        r=row(0);p=predict(r,(.3,.3,-.3,1.2));r["y"]=2
        self.assertEqual(p,predict(r,(.3,.3,-.3,1.2)))
    def test_fit_scope_and_grid(self):
        rows=[row(i) for i in range(210)]
        par=fit(rows);self.assertEqual(len(par),4)
        rows[-1]["season"]="2025-26"
        with self.assertRaisesRegex(ValueError,"DEVELOPMENT"):fit(rows)
    def test_outsider_is_fixed_reference_and_bad_rates(self):
        r=row(2);r["candidate"]=[.2,.2,.6]
        d=diagnostic([r],"candidate")
        self.assertEqual(d["reference_outsider_observed"],1)
        self.assertAlmostEqual(d["reference_outsider_mean_probability"],.6)
        r["home_rate"]=0.
        with self.assertRaisesRegex(ValueError,"RATES"):predict(r,(0.,0.,0.,1.))
