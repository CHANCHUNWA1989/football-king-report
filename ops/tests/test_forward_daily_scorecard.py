"""Daily forward scorecard tests, all data synthetic."""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forward_daily_scorecard import build, publish

BASE = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def row(i, y=0):
    kickoff = BASE + timedelta(days=i)
    return {"key": str(i), "league": "epl",
            "kickoff_utc": kickoff.isoformat(),
            "forecast_utc": (kickoff-timedelta(hours=2)).isoformat(),
            "market_utc": (kickoff-timedelta(hours=3)).isoformat(),
            "p": [.8, .1, .1], "m": [.1, .1, .8], "y": y,
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED"}


def evidence(rows):
    return {"schema": "football-king-forward-research-1",
            "checked_utc": BASE.isoformat(), "samples": rows, "n": len(rows),
            "results_independently_verified": False,
            "profitability_verified": False,
            "production_recommendations": "DISABLED"}


class DailyScorecardTests(unittest.TestCase):
    def test_same_settled_cases_and_correct_weights(self):
        report = build(evidence([row(0), row(1)]))
        self.assertEqual(report["settled_observations"], 2)
        self.assertEqual(report["remaining_to_target"], 998)
        self.assertEqual(report["cumulative"]["0.00"]["correct"], 2)
        self.assertEqual(report["cumulative"]["0.50"]["correct"], 2)
        self.assertEqual(report["cumulative"]["0.75"]["correct"], 0)
        self.assertEqual(report["cumulative"]["1.00"]["correct"], 0)
        self.assertEqual(len(report["daily_utc"]), 2)
        self.assertFalse(report["statistical_superiority_proven"])
        self.assertFalse(report["results_independently_verified"])

    def test_missing_settlement_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                publish(Path(d) / "missing.json", Path(d) / "site")
            self.assertFalse((Path(d) / "site" / "forward_daily_scorecard.json").exists())

    def test_empty_is_hold(self):
        report = build(evidence([]))
        self.assertEqual(report["status"], "HOLD")
        self.assertIsNone(report["cumulative"]["0.00"])

    def test_invalid_sealed_rows_rejected(self):
        bad = row(0)
        bad["forecast_utc"] = (BASE+timedelta(hours=1)).isoformat()
        with self.assertRaises(ValueError):
            build(evidence([bad]))


if __name__ == "__main__":
    unittest.main()
