import unittest
from datetime import date,timedelta
from ops.date_only_temperature_replay import evaluate,MODELS


def fixture(n=160):
    days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(n)]
    vectors={m:[{"HOME":.8,"DRAW":.1,"AWAY":.1} for _ in days] for m in MODELS}
    outcomes=[("HOME","DRAW","AWAY","HOME")[i%4] for i in range(n)]
    return days,vectors,outcomes


class DateOnlyTemperatureTests(unittest.TestCase):
    def test_fit_validation_and_embargo(self):
        d,v,y=fixture()
        r=evaluate(d,v,y)
        self.assertEqual((r["fit_n"],r["validation_n"],r["embargo_excluded_n"]),(119,40,1))
        for m in MODELS:
            x=r["model_reports"][m]
            self.assertGreater(x["temperature_fit_only"],1.)
            self.assertTrue(x["research_both_metrics_improved"])
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["model_promoted"])

    def test_validation_outcomes_cannot_change_fitted_temperature(self):
        d,v,y=fixture()
        a=evaluate(d,v,y)
        b=evaluate(d,v,y[:120]+["HOME"]*40)
        for m in MODELS:
            self.assertEqual(a["model_reports"][m]["temperature_fit_only"],
                             b["model_reports"][m]["temperature_fit_only"])
            self.assertFalse(b["model_reports"][m]["research_both_metrics_improved"])

    def test_same_date_kept_together(self):
        d,v,y=fixture()
        d[119]=d[120]
        r=evaluate(d,v,y)
        self.assertEqual(r["validation_n"],41)
        self.assertEqual(r["fit_n"],119)

    def test_small_cohort_and_invalid_probability(self):
        d,v,y=fixture(30)
        self.assertEqual(evaluate(d,v,y)["reason"],"INSUFFICIENT_CALIBRATION_SPLIT")
        v["poisson"][0]["HOME"]=True
        with self.assertRaises(ValueError):
            evaluate(d,v,y)


if __name__=="__main__":
    unittest.main()
