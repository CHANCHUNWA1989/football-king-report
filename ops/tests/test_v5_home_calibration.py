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


    def test_favorite_cohorts_are_fixed_by_baseline_not_outcome_or_candidate(self):
        e = evidence()
        for i, row in enumerate(e["samples"][60:]):
            row["p"] = [.65,.2,.15] if i < 10 else (
                [.15,.2,.65] if i < 20 else [.4,.25,.35])
            row["y"] = 0 if i < 5 else 2
        split = build(e)["retrospective_split"]
        g = split["favorite_diagnostics"]
        self.assertEqual(g["home_favorite"]["n"], 10)
        self.assertEqual(g["away_favorite"]["n"], 10)
        self.assertEqual(g["other"]["n"], 10)
        self.assertEqual(g["home_favorite"]["actual_favorite_wins"], 5)
        self.assertEqual(g["away_favorite"]["actual_favorite_wins"], 10)
        self.assertAlmostEqual(g["home_favorite"]["baseline_gap"], .15)
        self.assertAlmostEqual(g["away_favorite"]["baseline_gap"], -.35)
        self.assertEqual(g["home_favorite"]["coverage"], "INSUFFICIENT")
        self.assertEqual(g["away_favorite"]["coverage"], "INSUFFICIENT")
        for row in e["samples"][60:]:
            row["y"] = 1
        changed = build(e)["retrospective_split"]
        self.assertEqual(split["parameters"], changed["parameters"])
        for key in ("home_favorite", "away_favorite", "other"):
            self.assertEqual(g[key]["n"], changed["favorite_diagnostics"][key]["n"])
        self.assertEqual(changed["favorite_diagnostics"]["home_favorite"]["actual_favorite_wins"], 0)

    def test_favorite_empty_group_and_boundary(self):
        e = evidence()
        e["samples"][60]["p"] = [.6,.2,.2]
        e["samples"][61]["p"] = [.599,.201,.2]
        g = build(e)["retrospective_split"]["favorite_diagnostics"]
        self.assertEqual(g["home_favorite"]["n"], 29)
        self.assertEqual(g["other"]["n"], 1)
        self.assertEqual(g["away_favorite"]["n"], 0)
        self.assertIsNone(g["away_favorite"]["baseline_gap"])
        self.assertIsNone(g["away_favorite"]["candidate"])
        self.assertEqual(g["home_favorite"]["coverage"], "DESCRIPTIVE_ONLY")
        self.assertFalse(g["home_favorite"]["model_advantage_proven"])


    def test_heldout_regression_veto_blocks_new_candidate_forecast(self):
        e = evidence()
        for row in e["samples"][60:]:
            row["y"] = 0
        report = build(e)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["reason"], "HOLDOUT_DID_NOT_IMPROVE_BOTH_SCORES")
        self.assertIsNone(report["training_model"])
        self.assertFalse(report["retrospective_split"]["candidate_passes_score_gate"])
        now = datetime(2026,10,21,12,tzinfo=UTC)
        row = {"model":"poisson-shrinkage-unvalidated-v4.1", "league":"bundesliga",
               "event_id":"synthetic-test-only",
               "prediction_utc":(now-timedelta(minutes=5)).isoformat(),
               "kickoff_utc":(now+timedelta(hours=2)).isoformat(),
               "p_home":.65,"p_draw":.2,"p_away":.15,
               "production_recommendations":"DISABLED"}
        with self.assertRaisesRegex(ValueError, "NO_TRAINED_CANDIDATE"):
            forecast(e, row, now)

if __name__=="__main__":
    unittest.main()
