import unittest
from ops.offline_1x2_validation import evaluate_1x2

class TestOffline1X2(unittest.TestCase):
    def test_scores(self):
        r=evaluate_1x2([{"event_id":"match1",
             "probabilities":{"H":.7,"D":.2,"A":.1},"outcome":"H"}])
        self.assertEqual(r["sample_count"],1)
        self.assertAlmostEqual(r["brier"],.14)
        self.assertEqual(r["accuracy"],1)
        self.assertAlmostEqual(r["expected_confidence_calibration_error"],.3)
        self.assertEqual(r["confidence_calibration_bins"][0]["count"],1)

    def test_invalid_probabilities_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_1x2([{"event_id":"match1",
                "probabilities":{"H":.7,"D":.2,"A":.2},"outcome":"H"}])

    def test_csv_pregame_validation(self):
        import tempfile
        from pathlib import Path
        from ops.offline_1x2_csv import review_csv
        header="event_id,forecast_at,kickoff_at,settled_at,home_prob,draw_prob,away_prob,outcome"
        valid="a,2026-01-01T09:00:00Z,2026-01-01T10:00:00Z,2026-01-01T12:00:00Z,.7,.2,.1,H"
        invalid="a,2026-01-01T11:00:00Z,2026-01-01T10:00:00Z,2026-01-01T12:00:00Z,.7,.2,.1,H"
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"forecasts.csv"
            path.write_text(chr(10).join([header,valid]) + chr(10))
            self.assertEqual(review_csv(path)["sample_count"],1)
            path.write_text(chr(10).join([header,invalid]) + chr(10))
            with self.assertRaises(ValueError):
                review_csv(path)

    def test_holdout_training_prior_only(self):
        from ops.offline_1x2_holdout import holdout_1x2
        rows=[]
        for i in range(10):
            rows.append({"event_id":str(i),
                "forecast_at":f"2026-01-{i+1:02d}T09:00:00Z",
                "kickoff_at":f"2026-01-{i+1:02d}T10:00:00Z",
                "settled_at":f"2026-01-{i+1:02d}T12:00:00Z",
                "probabilities":{"H":.7,"D":.2,"A":.1},
                "outcome":"H" if i<7 else "A"})
        result=holdout_1x2(rows)
        self.assertEqual(result["test_count"],3)
        self.assertTrue(result["train_settlement_cutoff_verified"])
        self.assertEqual(result["research_screen"],"HOLD")
        self.assertEqual(result["research_screen_reason"],"insufficient_holdout_sample")
        self.assertEqual(result["minimum_research_holdout"],30)
        self.assertAlmostEqual(result["holdout_confidence_calibration_improvement_vs_train_prior"],
            result["train_prior_baseline"]["expected_confidence_calibration_error"]-
            result["holdout"]["expected_confidence_calibration_error"],places=7)
        self.assertAlmostEqual(result["holdout_logloss_improvement_vs_train_prior"],
                               result["train_prior_baseline"]["log_loss"]-result["holdout"]["log_loss"],places=7)
        self.assertAlmostEqual(result["train_prior_baseline"]["brier"],2.0)
        with self.assertRaises(ValueError):
            holdout_1x2(rows[::-1])

    def test_holdout_rejects_train_outcome_settled_after_test_forecast(self):
        from ops.offline_1x2_holdout import holdout_1x2
        rows=[]
        for i in range(10):
            rows.append({"event_id":str(i),
                "forecast_at":f"2026-01-{i+1:02d}T09:00:00Z",
                "kickoff_at":f"2026-01-{i+1:02d}T10:00:00Z",
                "settled_at":f"2026-01-{i+1:02d}T12:00:00Z",
                "probabilities":{"H":.7,"D":.2,"A":.1},
                "outcome":"H"})
        rows[6]["settled_at"]="2026-01-08T09:30:00Z"
        with self.assertRaisesRegex(ValueError,"Training outcomes"):
            holdout_1x2(rows)

    def test_holdout_csv_cli_integration(self):
        import tempfile
        from pathlib import Path
        from ops.offline_1x2_holdout_cli import holdout_csv
        header="event_id,forecast_at,kickoff_at,settled_at,home_prob,draw_prob,away_prob,outcome"
        rows=[header]
        for i in range(10):
            d=f"2026-01-{i+1:02d}"
            rows.append(f"{i},{d}T09:00:00Z,{d}T10:00:00Z,{d}T12:00:00Z,.7,.2,.1,H")
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"predictions.csv"
            path.write_text(chr(10).join(rows)+chr(10))
            result=holdout_csv(path)
            self.assertEqual(result["test_count"],3)
            self.assertIn("holdout_logloss_improvement_vs_train_prior",result)


    def test_simultaneous_football_fixtures_in_training(self):
        from ops.offline_1x2_holdout import holdout_1x2
        rows=[{"event_id":str(i),
               "forecast_at":f"2026-01-{i+1:02d}T09:00:00Z",
               "kickoff_at":f"2026-01-{i+1:02d}T10:00:00Z",
               "settled_at":f"2026-01-{i+1:02d}T12:00:00Z",
               "probabilities":{"H":0.6,"D":0.2,"A":0.2},
               "outcome":"H"}
              for i in range(10)]
        rows[1]["kickoff_at"]=rows[0]["kickoff_at"]
        rows[1]["forecast_at"]="2026-01-01T09:30:00Z"
        rows[1]["settled_at"]="2026-01-01T13:00:00Z"
        self.assertEqual(holdout_1x2(rows)["test_count"],3)

    def test_duplicate_event_rejected(self):
        row={"event_id":"match1","probabilities":{"H":.7,"D":.2,"A":.1},"outcome":"H"}
        with self.assertRaises(ValueError):
            evaluate_1x2([row,row])

if __name__=="__main__":
    unittest.main()
