"""Regression: reject oversized research ledgers before result-file access."""
import tempfile
import unittest
from pathlib import Path
from ops.offline_1x2_ledger_settlement import settle_ledger as settle


class SettlementInputLimitTests(unittest.TestCase):
    def test_oversized_forecast_ledger_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "forecasts.jsonl"
            ledger.write_text("{}\\n" * 100001, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Forecast row limit exceeded"):
                settle(ledger, Path(directory) / "missing_results.csv")


if __name__ == "__main__":
    unittest.main()
