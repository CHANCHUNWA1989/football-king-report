"""Tests for autonomous health guard safety gates."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autonomous_health_guard import inspect_document, audit, check_consistency


class HealthGuardTests(unittest.TestCase):
    def test_valid_research_hold(self):
        self.assertEqual(inspect_document("validation.json", {"n": 24, "production_recommendations": "DISABLED"}), "OK")
        self.assertEqual(inspect_document("production_gate.json", {"status": "HOLD", "conditions": {}}), "OK")
        self.assertEqual(inspect_document("market_status.json", {"production_recommendations": "DISABLED"}), "OK")

    def test_unexpected_activation_fails_closed(self):
        self.assertEqual(inspect_document("validation.json", {"n": 24, "production_recommendations": "ENABLED"}), "UNSAFE_PRODUCTION_STATE")
        self.assertNotEqual(inspect_document("production_gate.json", {"status": "PASS"}), "OK")
        self.assertNotEqual(inspect_document("market_status.json", {"production_recommendations": "ENABLED"}), "OK")

    def test_bad_document_fails_closed(self):
        self.assertEqual(inspect_document("validation.json", []), "INVALID_JSON_OBJECT")
        self.assertEqual(inspect_document("validation.json", {"n": -1, "production_recommendations": "DISABLED"}), "INVALID_SAMPLE_COUNT")

    def test_published_counts_must_agree(self):
        self.assertEqual(check_consistency({"n": 24}, {"settled_samples": 24}), "OK")
        self.assertEqual(check_consistency({"n": 24}, {"settled_samples": 23}), "SETTLED_SAMPLE_COUNT_MISMATCH")
        self.assertEqual(check_consistency({"n": 24}, {"settled_samples": None}), "MISSING_OR_INVALID_COUNTS")

    def test_https_required(self):
        with self.assertRaises(ValueError):
            audit("http://example.com")


if __name__ == "__main__":
    unittest.main()
