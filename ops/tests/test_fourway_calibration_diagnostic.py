import copy
import unittest
from datetime import datetime,timedelta,timezone
from model_ab import candidate as b, MODEL as B
from model_market_challenger import candidate as c, MODEL as C
from fourway_calibration_diagnostic import build, report_diagnostic

class FourWayCalibrationTests(unittest.TestCase):
    def row(self,k=0,week=0,league="epl"):
        ko=datetime(2026,1,5,12,tzinfo=timezone.utc)+timedelta(weeks=week,minutes=k)
        p,m=[.6,.2,.2],[.4,.3,.3]
        return dict(key=str(k),league=league,kickoff_utc=ko.isoformat(),
                    forecast_utc=(ko-timedelta(hours=1)).isoformat(),
                    market_utc=(ko-timedelta(hours=2)).isoformat(),p=p,m=m,
                    ab=b(p),ab_model=B,c=c(p,m),c_model=C,y=k%3,
                    fixture_result_source_independently_verified=False,
                    production_recommendations="DISABLED")
    def run_rows(self,rows):
        return build(rows,checked_utc="2026-12-01T00:00:00Z")
    def test_exact_same_cohort_and_immutable_inputs(self):
        rows=[self.row(0),self.row(1)]
        del rows[1]["c"];del rows[1]["c_model"]
        original=copy.deepcopy(rows)
        out=self.run_rows(rows)
        self.assertEqual(out["cohort_count"],1)
        self.assertEqual(out["excluded_count"],1)
        self.assertEqual(rows,original)
        for model in out["models"].values():
            self.assertEqual(model["n"],1)
            for cls in model["class_calibration"].values():
                self.assertEqual(sum(x["n"] for x in cls["bins"]),1)
        self.assertIsNone(out["paired_market_differences"]["A"]["log_loss_ci95"])
        self.assertFalse(out["positive_ev_verified"])
    def test_malformed_duplicate_and_fake_challenger_rejected(self):
        r=self.row()
        for rows in ([r,r],[dict(r,c=[.9,.05,.05])],[dict(r,y=True)],
                     [dict(r,fixture_result_source_independently_verified=True)]):
            with self.assertRaises(ValueError):self.run_rows(rows)
    def test_immature_outcome_rejected(self):
        with self.assertRaises(ValueError):
            build([self.row()],checked_utc="2026-01-05T13:00:00Z")
    def test_week_blocks_threshold_and_repeatability(self):
        leagues=("epl","bundesliga","laliga","seriea")
        rows=[self.row(i,i%12,leagues[i%4]) for i in range(300)]
        a=self.run_rows(rows);d=self.run_rows(rows)
        self.assertTrue(a["descriptive_coverage_met"])
        self.assertEqual(a,d)
        self.assertEqual(a["hk_week_blocks"],12)
        for item in a["paired_market_differences"].values():
            self.assertEqual(len(item["log_loss_ci95"]),2)
            self.assertLessEqual(*item["log_loss_ci95"])
        self.assertEqual(a["authenticated_forward_samples"],0)
        self.assertFalse(a["promotion_allowed"])
    def test_legacy_report_isolated_without_admitting_missing_provenance(self):
        row=self.row()
        del row["fixture_result_source_independently_verified"]
        with self.assertRaises(ValueError):
            self.run_rows([row])
        out=report_diagnostic([row],checked_utc="2026-12-01T00:00:00Z")
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["cohort_count"],0)
        self.assertEqual(out["excluded_count"],1)
        self.assertEqual(out["models"],{})
        self.assertFalse(out["promotion_allowed"])

    def test_empty_holds(self):
        self.assertEqual(self.run_rows([])["status"],"HOLD")

if __name__=="__main__":
    unittest.main()
