import unittest
from ops.v8_ucl_calibration import calibrate,fit,evaluate,profile
def cases():
    return [{"date":"2024-09-17" if i<240 else "2025-09-16","season":"2024-25" if i<240 else "2025-26",
        "home":str(i),"away":"a","hybrid":[.6,.2,.2],"y":i%3} for i in range(384)]
class UCLCalibrationTests(unittest.TestCase):
    def test_identity(self):
        for a,b in zip(calibrate([.5,.3,.2],1.,0.,0.),[.5,.3,.2]):self.assertAlmostEqual(a,b)
    def test_shift_direction(self):
        self.assertLess(calibrate([.5,.3,.2],1.,-.6,0.)[0],.5)
        self.assertGreater(calibrate([.5,.3,.2],1.,0.,.6)[1],.3)
    def test_fit_no_assessment(self):
        with self.assertRaisesRegex(ValueError,"LEAKAGE"):fit(cases())
    def test_test_outcomes_cannot_change_fit(self):
        a=cases();b=cases()
        for r in b[240:]:r["y"]=0
        x,y=evaluate(a),evaluate(b)
        self.assertEqual(x["parameters"],y["parameters"])
        self.assertFalse(x["automatic_promotion"])
    def test_profile(self):
        a=profile(cases()[:3],lambda r:r["hybrid"])
        self.assertEqual(a[0]["top_prediction_count"],3)
        self.assertAlmostEqual(a[1]["observed"],1/3)
    def test_duplicate(self):
        a=cases()
        with self.assertRaisesRegex(ValueError,"INVALID_CASE"):evaluate(a+[a[0]])
