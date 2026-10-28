"""Tests for the read-only market diagnostics."""
import unittest
from datetime import datetime, timezone
from ops.market_diagnostics import diagnose


class MarketDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.now = "2026-10-28T10:30:00+00:00"
        self.base = {
            "as_of_utc": "2026-10-28T10:29:00+00:00",
            "status": "RESEARCH_ONLY",
            "quota": {"used": 10, "remaining": 490},
            "quota_policy": {"max_monthly_used": 360, "remaining_floor": 140},
            "requested_markets": ["h2h", "totals", "spreads"],
            "handicap_and_totals_verified": True,
        }

    def test_healthy_research_still_cannot_bet(self):
        result = diagnose(self.base, now_utc=self.now)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["betting_permission"])
        self.assertEqual(result["provider_calls_made"], 0)

    def test_quota_and_missing_totals(self):
        case = {**self.base, "quota": {"used": 358, "remaining": 142},
                "quota_policy": {"max_monthly_used": 360, "remaining_floor": 142},
                "requested_markets": ["h2h"],
                "handicap_and_totals_verified": False}
        result = diagnose(case, now_utc=self.now)
        self.assertIn("API_QUOTA_GUARD", result["blockers"])
        self.assertIn("TOTALS_MARKET_NOT_REQUESTED", result["blockers"])
        self.assertIn("HANDICAP_TOTALS_NOT_VERIFIED", result["blockers"])

    def test_stale_snapshot(self):
        case = {**self.base, "as_of_utc": "2026-10-26T01:45:58+00:00"}
        self.assertIn("MARKET_SNAPSHOT_STALE_OR_UNDATED",
                      diagnose(case, now_utc=self.now)["blockers"])

    def test_missing_snapshot_fails_closed(self):
        result = diagnose(None, now_utc=self.now)
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result.get("betting_permission", False))


if __name__ == "__main__":
    unittest.main()
