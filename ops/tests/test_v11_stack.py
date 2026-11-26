import unittest
from ops.v11_stack import features,fit_stack,prediction_set,quantile,predict,sets
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
