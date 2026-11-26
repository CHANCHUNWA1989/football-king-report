import unittest
from datetime import date,timedelta
from ops.v9_schedule_venue import features,adjust,fit
D=date(2025,8,1)
class ScheduleTests(unittest.TestCase):
    def test_missing_neutral(self):
        r=features([(D,"A","B",1,0)])
        self.assertIsNone(r[D.isoformat(),"A","B"])
        self.assertEqual(adjust([.5,.3,.2],None,(.2,.2,.2)),[.5,.3,.2])
    def test_direction(self):
        self.assertGreater(adjust([.5,.3,.2],(1,1,1),(.2,.2,.2))[0],.5)
    def test_same_day(self):
        a=[(D,"A","C",1,0),(D,"B","D",1,0),(D+timedelta(days=7),"A","B",0,1),(D+timedelta(days=7),"C","D",1,0)]
        b=list(a);b[2]=(a[2][0],"A","B",8,0)
        self.assertEqual(features(a),features(b))
    def test_rest(self):
        a=[(D,"A","C",1,0),(D+timedelta(days=4),"B","D",1,0),(D+timedelta(days=7),"A","B",0,1)]
        self.assertGreater(features(a)[a[-1][0].isoformat(),"A","B"][0],0)
    def test_duplicate(self):
        r=(D,"A","B",1,0)
        with self.assertRaisesRegex(ValueError,"INVALID"):features([r,r])
    def test_assessment_leakage(self):
        with self.assertRaisesRegex(ValueError,"DEVELOPMENT"):fit([{"season":"2025-26","date":"2025-08-01"}]*500)
