import unittest
from datetime import datetime,timedelta,timezone
from ops.v9_feature_calibration import rates,xg_cases,xg_predict,lineup_predict,evaluate
D=datetime(2024,8,1,tzinfo=timezone.utc)

def row(i):
    d=D+timedelta(days=i)
    return {"id":str(i),"home":"A" if i%2==0 else "B","away":"B" if i%2==0 else "A",
            "ko":d,"available":d+timedelta(hours=3),"goals":(2,1),"xg":(1.6,.7)}

class FeatureCalibrationTests(unittest.TestCase):
    def test_role_independent_history_and_no_future(self):
        h=[row(i) for i in range(30)]
        p=rates(h,"A","B",D+timedelta(days=31),"xg")
        self.assertIsNotNone(p)
        with self.assertRaisesRegex(ValueError,"FUTURE_HISTORY"):rates(h,"A","B",D+timedelta(days=29),"xg")
    def test_same_day_and_late_xg_not_used(self):
        rows=[row(i) for i in range(30)]
        a=xg_cases(rows)
        b=[dict(r) for r in rows];b[-1]["xg"]=(9.,0.)
        self.assertEqual(a[-1]["xg_rates"],xg_cases(b)[-1]["xg_rates"])
        b[-2]["available"]=b[-1]["ko"]+timedelta(hours=1)
        self.assertNotEqual(a[-1]["xg_rates"],xg_cases(b)[-1]["xg_rates"])
        self.assertEqual(xg_predict(a[-1],0.),a[-1]["baseline"])
    def test_lineup_direction_and_zero_weight(self):
        r={"baseline":[.5,.3,.2],"rating_delta":.4}
        self.assertEqual(lineup_predict(r,0.),r["baseline"])
        self.assertGreater(lineup_predict(r,1.)[0],.5)
    def test_delayed_labels_and_assessment_mutation(self):
        rows=[]
        for i in range(180):
            r=row(i);r.update(y=i%3,date=r["ko"].date().isoformat(),baseline=[.5,.3,.2],
                              rating_delta=.2,changes=2)
            rows.append(r)
        split=D+timedelta(days=120);end=D+timedelta(days=181)
        rows[119]["available"]=split+timedelta(hours=1)
        a=evaluate(rows,split,end,"lineup")
        self.assertEqual(a["training_n"],119)
        other=[dict(r) for r in rows]
        for r in other[120:]:r["y"]=(r["y"]+1)%3
        self.assertEqual(a["selected_parameter"],evaluate(other,split,end,"lineup")["selected_parameter"])
        self.assertEqual(a["verified_forward_sample_credit"],0)
        self.assertEqual(evaluate(rows[:10],split,end,"lineup")["reason"],"INSUFFICIENT_CHRONOLOGICAL_COHORT")
