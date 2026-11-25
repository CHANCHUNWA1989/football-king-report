import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from ops.offline_1x2_holdout_cli import COLUMNS, holdout_csv
from ops.offline_1x2_validation import evaluate_1x2

class TestOffline1X2(unittest.TestCase):
    def test_scores(self):
        r=evaluate_1x2([{"event_id":"match1",
             "probabilities":{"H":.7,"D":.2,"A":.1},"outcome":"H"}])
        self.assertEqual(r["sample_count"],1)
        self.assertAlmostEqual(r["brier"],.14)
        self.assertEqual(r["accuracy"],1)
        low,high=r["accuracy_wilson_95pct_interval"]
        self.assertLess(low,r["accuracy"])
        self.assertEqual(high,1.0)
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

    def test_football_forecast_ledger_rejects_late_duplicate_and_invalid(self):
        import tempfile
        from pathlib import Path
        from ops.offline_1x2_ledger import append_forecast
        record={"event_id":"match-1","forecast_at":"2026-01-01T09:00:00Z",
                "kickoff_at":"2026-01-01T10:00:00Z",
                "probabilities":{"H":0.6,"D":0.2,"A":0.2}}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"forecasts.jsonl"
            self.assertTrue(append_forecast(path,record)["saved"])
            with self.assertRaises(ValueError):
                append_forecast(path,record)
            with self.assertRaises(ValueError):
                append_forecast(path,{**record,"event_id":"late",
                    "forecast_at":"2026-01-01T11:00:00Z"})
            with self.assertRaises(ValueError):
                append_forecast(path,{**record,"event_id":"invalid",
                    "probabilities":{"H":0.6,"D":0.3,"A":0.3}})
            self.assertEqual(len(path.read_text().splitlines()),1)

    def test_football_ledger_settlement_matches_results(self):
        import tempfile
        from pathlib import Path
        from ops.offline_1x2_ledger import append_forecast
        from ops.offline_1x2_ledger_settlement import settle_ledger
        with tempfile.TemporaryDirectory() as folder:
            ledger=Path(folder)/"forecasts.jsonl"
            results=Path(folder)/"results.csv"
            for i in range(2):
                append_forecast(ledger,{"event_id":str(i),
                    "forecast_at":"2026-01-01T09:00:00Z",
                    "kickoff_at":"2026-01-01T10:00:00Z",
                    "probabilities":{"H":0.7,"D":0.2,"A":0.1}})
            results.write_text("event_id,settled_at,outcome\n"
                "0,2026-01-01T12:00:00Z,H\n")
            report=settle_ledger(ledger,results)
            self.assertEqual(report["settled_count"],1)
            self.assertEqual(report["unsettled_count"],1)
            self.assertAlmostEqual(report["score"]["brier"],0.14)
            from ops.offline_1x2_ledger_cli import main
            from contextlib import redirect_stdout
            from io import StringIO
            with redirect_stdout(StringIO()) as output:
                cli_report=main(["--ledger",str(ledger),"--results",str(results)])
            self.assertEqual(cli_report["settled_count"],1)
            self.assertIn('"settled_count": 1',output.getvalue())
            results.write_text("event_id,settled_at,outcome\n"
                "0,2026-01-01T08:00:00Z,H\n")
            with self.assertRaises(ValueError):
                settle_ledger(ledger,results)
            results.write_text("event_id,settled_at,outcome\\n0,2026-01-01T12:00:00Z\\n")
            with self.assertRaises(ValueError):
                settle_ledger(ledger,results)

    def test_duplicate_event_rejected(self):
        row={"event_id":"match1","probabilities":{"H":.7,"D":.2,"A":.1},"outcome":"H"}
        with self.assertRaises(ValueError):
            evaluate_1x2([row,row])


class TestHoldoutWorkflow(unittest.TestCase):
    def setUp(self):
        self.repo = Path(__file__).resolve().parent
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.summary = self.folder / "step-summary.md"
        self.report = self.folder / "football-holdout-report.json"
        workflow = self.repo / ".github/workflows/football-holdout-report.yml"
        heredoc = re.search(r"^ +python - <<'PY'\n(.*?)^ +PY$", workflow.read_text(),
                            flags=re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(heredoc, "Holdout report workflow must execute this Python heredoc")
        self.script = textwrap.dedent(heredoc.group(1))

    def run_holdout(self, csv_path="forecasts.csv", event="schedule"):
        return subprocess.run(
            [sys.executable, "-"],
            input=self.script,
            text=True,
            capture_output=True,
            cwd=self.folder,
            env={
                **os.environ,
                "CSV_PATH": csv_path,
                "GITHUB_EVENT_NAME": event,
                "GITHUB_STEP_SUMMARY": str(self.summary),
                "PYTHONPATH": str(self.repo),
            },
            check=False,
        )

    def assert_unverified_report(self, status, reason, **details):
        self.assertEqual(json.loads(self.report.read_text()), {
            "status": status,
            "reason": reason,
            "verified_samples": 0,
            "accuracy_verified": False,
            "real_betting_enabled": False,
            **details,
        })
        summary = self.summary.read_text()
        for expected in (status, reason, "0 verified samples", "Predictive accuracy is unverified"):
            self.assertIn(expected, summary)

    def test_scheduled_missing_csv_reports_zero_verified_samples(self):
        completed = self.run_holdout()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assert_unverified_report("NO_DATA", "Committed forecast CSV missing")

    def test_automatic_main_push_reports_missing_csv_without_scoring(self):
        completed = self.run_holdout(event="push")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assert_unverified_report("NO_DATA", "Committed forecast CSV missing")

    def test_invalid_csv_reports_a_hold_without_scoring(self):
        (self.folder / "forecasts.csv").write_text("unexpected,columns\n")
        completed = self.run_holdout()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assert_unverified_report(
            "HOLD", "Football historical CSV failed validation", error_type="ValueError",
        )

    def test_csv_parser_failure_reports_a_hold_without_scoring(self):
        oversized = "x" * (csv.field_size_limit() + 1)
        (self.folder / "forecasts.csv").write_text(oversized + "\n", encoding="utf-8")
        completed = self.run_holdout()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assert_unverified_report(
            "HOLD", "Football historical CSV failed validation", error_type="Error",
        )

    def test_valid_csv_keeps_existing_research_scores(self):
        csv = self.folder / "forecasts.csv"
        rows = [",".join(COLUMNS)]
        for day in range(1, 11):
            date = f"2026-01-{day:02d}"
            rows.append(f"{day},{date}T09:00:00Z,{date}T10:00:00Z,{date}T12:00:00Z,.7,.2,.1,H")
        csv.write_text("\n".join(rows) + "\n")

        completed = self.run_holdout(event="workflow_dispatch")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(self.report.read_text()), holdout_csv(csv))

    def test_manual_missing_csv_still_fails(self):
        completed = self.run_holdout(event="workflow_dispatch")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("CSV must be committed inside repository", completed.stderr)
        self.assertFalse(self.report.exists())

    def test_unsafe_csv_paths_still_fail(self):
        (self.folder / "linked.csv").symlink_to(self.repo / "outside.csv")
        for path in ("../forecasts.csv", "/forecasts.csv", "forecasts.json", "linked.csv"):
            with self.subTest(path=path):
                completed = self.run_holdout(csv_path=path)
                self.assertNotEqual(completed.returncode, 0)
                self.assertFalse(self.report.exists())


if __name__=="__main__":
    unittest.main()
