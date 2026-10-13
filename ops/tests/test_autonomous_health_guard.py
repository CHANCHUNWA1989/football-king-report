"""Tests for autonomous health guard safety gates."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autonomous_health_guard import inspect_document, audit, check_consistency, check_market_freshness


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

    def test_market_freshness_fail_closed(self):
        now = datetime(2026, 10, 13, tzinfo=timezone.utc)
        def doc(dt):
            return {"market_as_of_utc": dt.isoformat()}
        self.assertEqual(check_market_freshness(doc(now - timedelta(hours=1)), now), "OK")
        self.assertEqual(check_market_freshness(doc(now - timedelta(days=4)), now), "STALE_MARKET_SNAPSHOT")
        self.assertEqual(check_market_freshness(doc(now + timedelta(days=1)), now), "FUTURE_MARKET_TIMESTAMP")
        self.assertEqual(check_market_freshness({"market_as_of_utc": "bad"}, now), "INVALID_MARKET_TIMESTAMP")
        self.assertEqual(check_market_freshness({}, now), "MISSING_MARKET_TIMESTAMP")

    def test_missing_cross_checks_cannot_pass(self):
        from unittest.mock import patch, MagicMock
        from io import BytesIO
        import json
        docs = {
            "validation.json": {"n": 24, "production_recommendations": "DISABLED"},
            "production_gate.json": {"status": "HOLD", "settled_samples": 24},
            "market_status.json": {"production_recommendations": "DISABLED", "market_as_of_utc": "2026-10-13T00:00:00Z"},
        }
        def fetch(request, timeout):
            name = request.full_url.rsplit("/", 1)[-1]
            if name == "production_gate.json":
                raise OSError("unavailable")
            response = MagicMock()
            response.status = 200
            response.read.return_value = json.dumps(docs[name]).encode()
            response.__enter__.return_value = response
            return response
        with patch("autonomous_health_guard.urlopen", side_effect=fetch):
            report = audit("https://example.com")
        self.assertEqual(report["status"], "HOLD")
        self.assertNotIn("sample_count_consistency", report["checks"])

    def test_https_required(self):
        with self.assertRaises(ValueError):
            audit("http://example.com")


if __name__ == "__main__":
    unittest.main()
