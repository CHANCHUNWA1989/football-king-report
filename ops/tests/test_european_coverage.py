"""Offline tests: no network calls or API credits."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from ops.european_coverage import CONFIG, audit


class TestEuropeanCoverage(unittest.TestCase):
    def test_default_is_fail_closed(self):
        result = audit()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(len(result["competitions"]), 8)
        self.assertFalse(result["league_ids_verified"])
        self.assertFalse(result["api_entitlements_verified"])
        self.assertFalse(result["live_odds_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_duplicate_competition_rejected(self):
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        data["competitions"][0] = copy.deepcopy(data["competitions"][1])
        self.assert_invalid(data)

    def test_enabled_production_rejected(self):
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        data["provider_policy"]["production_recommendations"] = "ENABLED"
        self.assert_invalid(data)

    def test_disabled_hold_rejected(self):
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        data["provider_policy"]["fallback"] = "CONTINUE"
        self.assert_invalid(data)

    def test_unsupported_schema_rejected(self):
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        data["schema_version"] = 2
        self.assert_invalid(data)

    def assert_invalid(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "coverage.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                audit(path)


if __name__ == "__main__":
    unittest.main()
