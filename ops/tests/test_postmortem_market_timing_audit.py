"""Synthetic tests for market timestamp claims, not market data."""
import unittest
from ops.postmortem_market_timing_audit import audit_market_timing


def row(key="fixture-1", **changes):
    return {"key": key, "kickoff_utc": "2026-01-01T12:00:00Z",
            "forecast_utc": "2026-01-01T11:50:00Z",
            "market_utc": "2026-01-01T11:48:00Z", **changes}


def archive(*rows):
    return {"schema": "football-king-forward-research-1",
            "n": len(rows), "samples": list(rows)}


class MarketTimingAuditTests(unittest.TestCase):
    def test_exact_boundary_and_no_promotion(self):
        out = audit_market_timing(archive(row()))
        self.assertEqual(out["prior_market_within_minutes"], {"2":1,"5":1,"20":1})
        self.assertEqual(out["prematch_market_within_kickoff_minutes"],
                         {"2":0,"5":0,"10":0,"60":1})
        self.assertEqual(out["market_to_forecast_gap_minutes"]["median"], 2)
        self.assertEqual(out["status"], "HOLD")
        self.assertFalse(out["closing_price_evidence_available"])
        self.assertFalse(out["opening_price_evidence_available"])
        self.assertFalse(out["raw_bookmaker_overround_available"])
        self.assertFalse(out["independent_same_time_comparison_certified"])

    def test_later_market_not_admitted(self):
        out = audit_market_timing(archive(row(market_utc="2026-01-01T11:51:00Z")))
        self.assertEqual(out["market_after_forecast"], 1)
        self.assertEqual(out["prior_market_within_minutes"], {"2":0,"5":0,"20":0})

    def test_timezone_equivalence_and_even_median(self):
        out = audit_market_timing(archive(row(), row("fixture-2",
             forecast_utc="2026-01-01T19:50:00+08:00",
             market_utc="2026-01-01T19:44:00+08:00")))
        self.assertEqual(out["market_to_forecast_gap_minutes"]["median"], 4)

    def test_post_kickoff_rejected(self):
        for changes in ({"market_utc":"2026-01-01T12:00:00Z"},
                        {"forecast_utc":"2026-01-01T12:01:00Z"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                audit_market_timing(archive(row(**changes)))

    def test_invalid_timestamp_rejected(self):
        for value in (None, True, "2026-01-01T11:48:00", "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                audit_market_timing(archive(row(market_utc=value)))

    def test_duplicate_and_count_mismatch(self):
        for payload in (archive(row(),row()), archive(row()) | {"n":2},
                        archive(row()) | {"n":True}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                audit_market_timing(payload)

    def test_empty_archive_stays_hold(self):
        out = audit_market_timing(archive())
        self.assertIsNone(out["market_to_forecast_gap_minutes"])
        self.assertEqual(out["certified_prospective_samples"], 0)


if __name__ == "__main__":
    unittest.main()
