import json
import tempfile
import unittest
from pathlib import Path
from research_quality.settlement_audit import audit, valid

def sample():
    return {"key": json.dumps(["epl", "home", "away", "2026-10-19T20:00:00+00:00"]),
            "league": "epl", "kickoff_utc": "2026-10-19T20:00:00+00:00",
            "forecast_utc": "2026-10-19T18:00:00+00:00",
            "market_utc": "2026-10-19T17:00:00+00:00",
            "y": 0, "p": [0.6, 0.2, 0.2], "m": [0.5, 0.3, 0.2],
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED"}

class SettlementAuditTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(valid(sample()))
    def test_future_forecast_rejected(self):
        r = sample()
        r["forecast_utc"] = "2026-10-19T21:00:00+00:00"
        self.assertFalse(valid(r))
    def test_invalid_market_rejected(self):
        r = sample()
        r["m"] = [1, 1, -1]
        self.assertFalse(valid(r))
    def test_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.json"
            path.write_text(json.dumps({"samples": [sample(), sample()]}))
            result = audit(path)
            self.assertEqual((result["accepted"], result["rejected"]), (1, 1))
            self.assertFalse(result["independently_verified"])
    def test_bad_provenance_rejected(self):
        r = sample()
        r["fixture_result_source_independently_verified"] = True
        self.assertFalse(valid(r))
