import copy
import json
import unittest
from datetime import datetime, timedelta, timezone

from ops.v5_home_calibration import build, calibrate, forecast

UTC = timezone.utc

def evidence():
    start = datetime(2026, 9, 7, 15, tzinfo=UTC)
    rows = []
    for i in range(90):
        k = start + timedelta(weeks=i//15, minutes=i%15)
        rows.append({"key": str(i), "league": "bundesliga", "y": 2 if i%3 else 1,
                     "p": [.65,.2,.15], "m": [.25,.35,.4],
                     "market_utc": (k-timedelta(hours=3)).isoformat(),
                     "forecast_utc": (k-timedelta(hours=2)).isoformat(),
                     "kickoff_utc": k.isoformat(), "production_recommendations": "DISABLED"})
    return {"schema":"football-king-forward-research-1", "n":len(rows), "samples":rows,
            "checked_utc":"2026-10-20T00:00:00+00:00", "production_recommendations":"DISABLED"}

class V5CalibrationTest(unittest.TestCase):
    def test_negative_home_shift(self):
        p=calibrate([.65,.2,.15], -.5, 1.0)
        self.assertLess(p[0], .65)
        self.assertAlmostEqual(sum(p),1)

    def test_fit_and_holdout_not_mutating(self):
        e=evidence()
        before=json.dumps(e, sort_keys=True)
        r=build(e)
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual(r["retrospective_split"]["train_n"],60)
        self.assertEqual(r["retrospective_split"]["test_n"],30)
        self.assertLess(r["training_model"]["home_logit_shift"],0)
        self.assertFalse(r["prospective_validation"])
        self.assertEqual(json.dumps(e,sort_keys=True), before)

    def test_holdout_labels_do_not_tune_split_parameters(self):
        e=evidence()
        r=build(e)
        for row in e["samples"][60:]:
            row["y"]=0
        self.assertEqual(r["retrospective_split"]["parameters"],
                         build(e)["retrospective_split"]["parameters"])

    def test_duplicate_and_time_leak_rejected(self):
        e=evidence()
        e["samples"][1]["key"]=e["samples"][0]["key"]
        with self.assertRaises(ValueError):
            build(e)
        e=evidence()
        e["samples"][0]["forecast_utc"]=e["samples"][0]["kickoff_utc"]
        with self.assertRaises(ValueError):
            build(e)

    def test_insufficient_archive(self):
        e=evidence()
        e["samples"]=e["samples"][:30]
        e["n"]=30
        self.assertEqual(build(e)["status"],"HOLD")

    def test_forecast_future_only(self):
        e=evidence()
        now=datetime(2026,10,21,12,tzinfo=UTC)
        row={"model":"poisson-shrinkage-unvalidated-v4.1","league":"bundesliga",
             "event_id":"synthetic-test-only","prediction_utc":(now-timedelta(minutes=5)).isoformat(),
             "kickoff_utc":(now+timedelta(hours=2)).isoformat(),
             "p_home":.65,"p_draw":.2,"p_away":.15,"production_recommendations":"DISABLED"}
        r=forecast(e,row,now)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertAlmostEqual(sum(r["p"]),1)
        for change in ({"kickoff_utc":now.isoformat()}, {"league":"ucl"}, {"score_ft":[1,0]},
                       {"prediction_utc":"2026-10-19T12:00:00+00:00"},
                       {"prediction_utc":(now+timedelta(minutes=1)).isoformat()}):
            with self.assertRaises(ValueError):
                forecast(e,{**row,**change},now)

if __name__=="__main__":
    unittest.main()
