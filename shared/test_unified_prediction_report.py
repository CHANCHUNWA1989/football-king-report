import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from shared.unified_prediction_report import main

P = dict(prediction_id="p1", system="quant", event_id="BTC-24h", created_at="2026-10-17T10:00:00+08:00", model_version="v1", market="BTC_DIRECTION", selection="up", probability=.6, odds=None, status="RESEARCH_ONLY")
O = dict(prediction_id="p1", outcome=1, actual_result_at="2026-10-18T10:00:00+08:00", verified=True, source="external-confirmation")

class ReportTests(unittest.TestCase):
    def test_json_report(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            predictions, outcomes, report = (root / name for name in ("predictions.jsonl", "outcomes.jsonl", "report.json"))
            predictions.write_text(json.dumps(P) + "\n", encoding="utf-8")
            outcomes.write_text(json.dumps(O) + "\n", encoding="utf-8")
            result = main(["--predictions", str(predictions), "--outcomes", str(outcomes), "--output", str(report)])
            self.assertEqual(result["evaluated"], 1)
            self.assertIsNone(result["roi"])
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["evaluated"], 1)
    def test_pending(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            predictions, outcomes = root / "p.jsonl", root / "o.jsonl"
            predictions.write_text(json.dumps(P) + "\n", encoding="utf-8")
            outcomes.write_text("", encoding="utf-8")
            self.assertEqual(main(["--predictions", str(predictions), "--outcomes", str(outcomes)])["pending"], 1)

if __name__ == "__main__":
    unittest.main()
