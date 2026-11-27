import copy
import unittest
from ops.v9_stacking_research import features,temper,combine,partition,fit_stack,select_calibration,EXPERTS

def row(i,season="2022-23",y=0):
    return {"league":"en.1","season":season,"date":season[:4]+"-09-01",
            "home":str(i),"away":"B","y":y,"experts":{k:[.5,.3,.2] for k in EXPERTS},
            "candidate":[.5,.3,.2],"hybrid":[.5,.3,.2]}

class StackTests(unittest.TestCase):
    def test_features_ignore_label_and_normalize(self):
        r=row(0);a=features(r);r["y"]=2
        self.assertEqual(a,features(r));self.assertEqual(len(a),16)
        self.assertAlmostEqual(sum(temper(r["candidate"],1.2)),1)
        self.assertEqual(combine([.1,.2,.7],r["candidate"],1.,0.),r["candidate"])
    def test_partition_rejects_duplicate_and_wrong_season(self):
        r=row(0)
        with self.assertRaisesRegex(ValueError,"INVALID_STACK_CASE"):partition([r,r])
        r["date"]="2025-09-01"
        with self.assertRaisesRegex(ValueError,"STACK_SEASON_CLOCK"):partition([r])
    def test_calibration_only_uses_calibration_season(self):
        rows=[row(i,"2024-25",i%3) for i in range(210)]
        p=[[.4,.3,.3]]*len(rows)
        t,w=select_calibration(rows,p)
        self.assertIn(t,(.8,1.,1.2,1.5));self.assertIn(w,(0.,.25,.5,.75,1.))
        rows[-1]["season"]="2025-26"
        with self.assertRaisesRegex(ValueError,"STACK_CAL_SCOPE"):select_calibration(rows,p)
    def test_fit_and_scope(self):
        try:import sklearn
        except ImportError:self.skipTest("optional ML dependency")
        rows=[row(i,y=i%3) for i in range(210)]
        model=fit_stack(rows)
        self.assertEqual(list(model.classes_),[0,1,2])
        self.assertAlmostEqual(sum(model.predict_proba([features(rows[0])])[0]),1)
        rows[-1]["season"]="2025-26"
        with self.assertRaisesRegex(ValueError,"STACK_TRAIN_SCOPE"):fit_stack(rows)
