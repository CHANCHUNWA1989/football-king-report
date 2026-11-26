import unittest
from ops.v11_stack import features,fit_stack,prediction_set,quantile,predict,sets,uncertainty_audit,league_screen
from ops.v5_ml_benchmark import BACKENDS
def row():
    return {"league":"en.1","season":"2024-25","date":"2024-09-01","y":0,"dc":[.5,.3,.2],
        "ml":[.6,.2,.2],"backends":{k:[.6,.2,.2] for k in BACKENDS},"stack":[.6,.2,.2]}
class StackTests(unittest.TestCase):
    def test_features(self):
        self.assertEqual(len(features(row())),33)
    def test_mean_conflict(self):
        r=row();r["ml"]=[.5,.3,.2]
        with self.assertRaisesRegex(ValueError,"ML_MEAN"):features(r)
    def test_stack_leakage(self):
        with self.assertRaisesRegex(ValueError,"STACK_LEAKAGE"):fit_stack([row()])
    def test_fallback(self):
        r=row();r["ml"]=None
        self.assertEqual(predict([r],None),[r["dc"]])
    def test_quantile(self):
        self.assertAlmostEqual(quantile([row()]*100),.4)
    def test_calibration_leakage(self):
        r=row();r["season"]="2025-26"
        with self.assertRaisesRegex(ValueError,"CALIBRATION_SCOPE"):quantile([r]*100)
    def test_set(self):
        self.assertEqual(prediction_set([.6,.2,.2],.4),[0])
        self.assertEqual(prediction_set([.4,.3,.3],.1),[0])
        self.assertEqual(sets([row()],.9)["three_outcome_n"],1)

    def test_uncertainty_audit_same_cohort(self):
        a={**row(),"stack":[.8,.1,.1],"v10":[.6,.2,.2]}
        b={**a,"date":"2025-01-02","y":1,"stack":[.8,.1,.1],"ml":None}
        c={**a,"stack":[.4,.35,.25],"y":2}
        d=uncertainty_audit([a,b,c],.7)
        self.assertEqual(d["singleton"]["n"],2)
        self.assertEqual(d["singleton"]["correct"],1)
        self.assertEqual(d["singleton"]["accuracy"],.5)
        self.assertEqual(d["singleton"]["same_fixture_metrics"]["stack"]["n"],2)
        self.assertEqual(d["non_singleton_abstention_n"],1)
        self.assertEqual(d["actual_outcomes"]["2"]["covered"],0)
        self.assertEqual(d["ml_fallback"]["n"],1)
        self.assertFalse(d["eligible_for_production"])
    def test_uncertainty_audit_no_singletons(self):
        a={**row(),"stack":[.4,.35,.25],"v10":[.4,.35,.25]}
        d=uncertainty_audit([a],.9)
        self.assertIsNone(d["singleton"]["accuracy"])
        self.assertIsNone(d["singleton"]["descriptive_wilson_95"])
        self.assertEqual(d["non_singleton_abstention_n"],1)
        self.assertIsNone(uncertainty_audit([], .9))

    def test_league_screen_fixed_calibration(self):
        cal=[{**row(),"home":f"H{i}","away":"A","stack":[.8,.1,.1],"y":0} for i in range(30)]
        test=[{**cal[0],"season":"2025-26","date":"2025-09-01","v10":[.6,.2,.2]}]
        a=league_screen(cal,test,.7)
        b=league_screen(cal,[{**test[0],"y":2}],.7)
        self.assertEqual(a["rules"],b["rules"])
        self.assertTrue(a["rules"]["en.1"]["eligible"])
        self.assertEqual(a["screened_singletons"]["correct"],1)
        self.assertEqual(b["screened_singletons"]["correct"],0)
        self.assertEqual(a["verified_forward_sample_credit"],0)
    def test_league_screen_small_sample_and_clock(self):
        cal=[{**row(),"home":"H","away":"A","stack":[.8,.1,.1]}]
        test=[{**cal[0],"season":"2025-26","date":"2025-09-01","v10":[.6,.2,.2]}]
        a=league_screen(cal,test,.7)
        self.assertFalse(a["rules"]["en.1"]["eligible"])
        self.assertEqual(a["abstention_n"],1)
        self.assertIsNone(a["screened_singletons"]["accuracy"])
        with self.assertRaisesRegex(ValueError,"LEAGUE_SCREEN_CLOCK"):league_screen(test,test,.7)
        with self.assertRaisesRegex(ValueError,"LEAGUE_SCREEN_DUPLICATE"):league_screen(cal+cal,test,.7)
