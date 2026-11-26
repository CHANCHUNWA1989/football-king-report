import unittest
from datetime import date,timedelta
from ops.v31_context_residual import features,adjust,select,GRID

class ContextResidualTests(unittest.TestCase):
    def test_same_day_and_future_scores_cannot_change_target_features(self):
        start=date(2025,1,1)
        rows=[(start+timedelta(days=i*3),"A","B",1,0) for i in range(5)]
        target=start+timedelta(days=15)
        x=rows+[(target,"A","C",1,0),(target,"B","D",0,1),(target,"A","B",2,0)]
        y=rows+[(target,"A","C",7,0),(target,"B","D",0,8),(target,"A","B",0,4),(target+timedelta(days=3),"A","B",0,9)]
        key=(target.isoformat(),"A","B")
        self.assertIsNotNone(features(x)[key])
        self.assertEqual(features(x)[key],features(y)[key])
    def test_mass_and_zero_fallback(self):
        row={"stack":[.5,.3,.2],"context":(.5,-.3,.7,.1)}
        self.assertEqual(adjust(row,(0.,0.,0.,0.)),row["stack"])
        for p in GRID:self.assertAlmostEqual(sum(adjust(row,p)),1.)
        self.assertEqual(adjust({**row,"context":None},(.2,.2,.2,.1)),row["stack"])
    def test_invalid_feature_and_assessment_refused(self):
        with self.assertRaisesRegex(ValueError,"CONTEXT_FEATURE"):
            adjust({"stack":[.5,.3,.2],"context":(float("nan"),0,0,0)},(.2,0,0,0))
        rows=[{"season":"2024-25","date":"2025-02-01","y":i%3,"stack":[1/3]*3,"context":None} for i in range(105)]
        self.assertEqual(select(rows),(0.,0.,0.,0.))
        rows[-1]["date"]="2025-07-01"
        with self.assertRaisesRegex(ValueError,"CAL_SCOPE"):select(rows)
