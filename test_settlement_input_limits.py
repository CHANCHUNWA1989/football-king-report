"""Regression checks for bounded, fail-closed offline settlement inputs."""
import tempfile
import unittest
from pathlib import Path
from ops.offline_1x2_ledger_settlement import settle_ledger as settle


class SettlementInputLimitTests(unittest.TestCase):
    def test_oversized_forecast_ledger_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "forecasts.jsonl"
            ledger.write_text("{}\n" * 100001, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Forecast row limit exceeded"):
                settle(ledger, Path(directory) / "missing_results.csv")

    def test_forecast_byte_limit_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "forecasts.jsonl"
            with ledger.open("wb") as handle:
                handle.truncate(33554433)
            with self.assertRaisesRegex(ValueError, "Forecast file size limit exceeded"):
                settle(ledger, Path(directory) / "missing_results.csv")

    def test_result_byte_limit_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "forecasts.jsonl"
            ledger.write_text("{}\n", encoding="utf-8")
            results = Path(directory) / "results.csv"
            with results.open("wb") as handle:
                handle.truncate(33554433)
            with self.assertRaisesRegex(ValueError, "Result file size limit exceeded"):
                settle(ledger, results)

    def test_result_row_limit_rejected_before_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "forecasts.jsonl"
            ledger.write_text("{}\n", encoding="utf-8")
            results = Path(directory) / "results.csv"
            with results.open("w", encoding="utf-8", newline="") as handle:
                handle.write("event_id,settled_at,outcome\n")
                handle.write("e,2026-10-17T00:00:00Z,1\n" * 100001)
            with self.assertRaisesRegex(ValueError, "Result row limit exceeded"):
                settle(ledger, results)


if __name__ == "__main__":
    unittest.main()
