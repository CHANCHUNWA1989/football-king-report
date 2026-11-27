import unittest
from datetime import datetime,timedelta,timezone
from ops.v9_market_calibration import probability,disagreement,evaluate
D=datetime(2026,9,1,tzinfo=timezone.utc)
def row(i):
    ko=D+timedelta(days=i//2,hours=12)
    return {"key":str(i),"kickoff":ko.isoformat(),"market_utc":(ko-timedelta(hours=2)).isoformat(),
            "forecast_utc":(ko-timedelta(hours=1)).isoformat(),"p":[.6,.2,.2],"m":[.4,.3,.3],"y":i%3}
class MarketCalibrationTests(unittest.TestCase):
    def test_exact_market_endpoint_and_mass(self):
        r=row(0)
        self.assertEqual(probability(r,0.,1.,"constant"),r["m"])
        a=probability(r,.25,1.,"constant");b=probability(r,.25,1.,"disagreement_damped")
        self.assertGreater(a[0],b[0]);self.assertAlmostEqual(sum(b),1)
        self.assertAlmostEqual(disagreement(r),.2)
    def test_embargo_and_assessment_mutation(self):
        rows=[row(i) for i in range(180)]
        split=(D+timedelta(days=60)).date().isoformat()
        a=evaluate(rows,split)
        self.assertEqual(a["development_n"],114)
        self.assertEqual(a["embargo_excluded_n"],6)
        self.assertEqual(a["assessment_n"],60)
        b=[dict(r,y=(r["y"]+1)%3) if i>=120 else r for i,r in enumerate(rows)]
        self.assertEqual(a["selected_parameters"],evaluate(b,split)["selected_parameters"])
        self.assertFalse(a["verified_ev"])
        self.assertEqual(a["verified_forward_sample_credit"],0)
    def test_bad_clock_and_small_sample(self):
        rows=[row(0)]
        self.assertEqual(evaluate(rows,"2026-10-01")["reason"],"INSUFFICIENT_COHORT")
        rows[0]["market_utc"]=rows[0]["kickoff"]
        with self.assertRaisesRegex(ValueError,"MARKET_CLOCK"):evaluate(rows,"2026-10-01")
