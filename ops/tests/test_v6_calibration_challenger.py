import unittest
from ops.v6_calibration_challenger import calibrate,fit,evaluate,WEIGHTS
from ops.v5_ensemble_competition import NAMES
def rows():
    return [{"league":"de.1","date":"2025-12-01" if i<120 else "2026-01-02","home":str(i),"away":"a","y":i%3,
             "base":[.6,.2,.2],"p":{k:[.6,.2,.2] for k in NAMES}} for i in range(240)]
class CalibrationTests(unittest.TestCase):
    def test_identity(self):
        for a,b in zip(calibrate([.5,.3,.2],1.,0.,0.),[.5,.3,.2]):self.assertAlmostEqual(a,b)
    def test_valid_mass(self):
        p=calibrate([1,0,0],1.5,.15,-.15)
        self.assertAlmostEqual(sum(p),1.)
        self.assertTrue(all(v>0 for v in p))
    def test_fit_refuses_assessment(self):
        with self.assertRaisesRegex(ValueError,"LEAKAGE"):fit(rows())
    def test_fit_small(self):
        with self.assertRaises(ValueError):fit(rows()[:99])
    def test_holdout_outcomes_do_not_change_params(self):
        a=rows();b=rows()
        for r in b[120:]:r["y"]=(r["y"]+1)%3
        x,y=evaluate(a),evaluate(b)
        self.assertEqual(x["params"],y["params"])
        self.assertFalse(x["automatic_promotion"])
        self.assertEqual(x["status"],"HOLD")
    def test_duplicate(self):
        a=rows()
        with self.assertRaises(ValueError):evaluate(a+[a[0]])
