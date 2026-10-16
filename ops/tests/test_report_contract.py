import unittest
from ops.report_contract import validate_report

class CommonReportTests(unittest.TestCase):
    def sample(self):
        return {"system": "football", "generated_at_utc": "2026-10-15T00:00:00Z",
                "source_status": {}, "forecast_count": 3, "settled_count": 1,
                "evaluation_metrics": {"brier_score": 0.25}, "failures": [], "version": "v1"}

    def test_valid(self):
        self.assertEqual(validate_report(self.sample())["forecast_count"], 3)

    def test_missing(self):
        row = self.sample()
        del row["version"]
        with self.assertRaises(ValueError):
            validate_report(row)

    def test_invalid_settlement(self):
        row = self.sample()
        row["settled_count"] = 4
        with self.assertRaises(ValueError):
            validate_report(row)

    def test_nan_metric(self):
        row = self.sample()
        row["evaluation_metrics"]["brier_score"] = float("nan")
        with self.assertRaises(ValueError):
            validate_report(row)

    def test_future_timestamp(self):
        row = self.sample()
        row["generated_at_utc"] = "2099-01-01T00:00:00Z"
        with self.assertRaises(ValueError):
            validate_report(row)

    def test_reject_bad_source_status(self):
        row = self.sample()
        row["source_status"] = {"provider": "OKAY"}
        with self.assertRaisesRegex(ValueError, "INVALID_SOURCE_STATUS"):
            validate_report(row)

    def test_reject_nonstring_system(self):
        row = self.sample()
        row["system"] = ["football"]
        with self.assertRaisesRegex(ValueError, "UNKNOWN_SYSTEM"):
            validate_report(row)

    def test_reference_clock(self):
        from datetime import datetime, timezone
        row = self.sample()
        with self.assertRaisesRegex(ValueError, "FUTURE_REPORT"):
            validate_report(row, now=datetime(2026, 10, 14, tzinfo=timezone.utc))
