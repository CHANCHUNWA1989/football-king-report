"""Requested markets never establish observed Asian handicap / totals coverage."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_coverage_audit import audit


def snapshot(**overrides):
    data = {
        "schema": "football-king-market-consensus-v1",
        "as_of_utc": "2026-11-02T02:02:25+00:00",
        "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
        "market": "h2h", "requested_markets": ["h2h"],
        "missing_markets": ["spreads", "totals"],
        "handicap_and_totals_verified": False,
        "raw_bookmaker_quotes_redistributed": False,
        "raw_bookmaker_names_redistributed": False,
        "model_value_advantage_verified": False,
        "event_count": 2, "events": [{"id": "one"}, {"id": "two"}],
    }
    data.update(overrides)
    return data


def summary(**overrides):
    data = {
        "schema": "football-king-public-artifact-summary-v1",
        "captured_utc": "2026-11-01T10:15:09Z",
        "requested_markets": ["h2h"],
        "production_recommendations": "DISABLED",
        "raw_prices_or_bookmakers_included": False,
        "quotes_are_executable": False, "verified_bets": 0,
    }
    data.update(overrides)
    return data


class MarketCoverageAuditTests(unittest.TestCase):
    def test_realistic_h2h_scope_reports_two_missing_markets(self):
        output = audit(snapshot(), summary())
        self.assertEqual(output["status"], "RESEARCH_ONLY")
        self.assertEqual(output["requested_markets"], ["h2h"])
        self.assertEqual(output["public_consensus_observed_markets"], ["h2h"])
        self.assertEqual(output["public_h2h_consensus_event_count"], 2)
        self.assertEqual(output["missing_markets"], ["spreads", "totals"])
        self.assertFalse(output["market_coverage_complete"])
        self.assertFalse(output["handicap_available"])
        self.assertFalse(output["totals_available"])
        self.assertFalse(output["raw_prices_verified"])
        self.assertFalse(output["can_recommend_handicap_or_totals"])
        self.assertEqual(output["production_recommendations"], "DISABLED")

    def test_claimed_three_market_request_cannot_become_observed_coverage(self):
        requested = summary(requested_markets=["h2h", "spreads", "totals"])
        output = audit(snapshot(), requested)
        self.assertEqual(output["requested_markets"],
                         ["h2h", "spreads", "totals"])
        self.assertEqual(output["public_consensus_observed_markets"], ["h2h"])
        self.assertEqual(output["missing_markets"], ["spreads", "totals"])
        self.assertFalse(output["handicap_available"])
        self.assertFalse(output["totals_available"])

    def test_empty_snapshot_returns_hold_with_no_public_h2h(self):
        output = audit(snapshot(event_count=0, events=[]), summary())
        self.assertEqual(output["status"], "HOLD")
        self.assertEqual(output["public_consensus_observed_markets"], [])
        self.assertEqual(output["missing_markets"], ["h2h", "spreads", "totals"])

    def test_invalid_public_snapshot_claims_cannot_promote_coverage(self):
        mutations = (
            {"schema": "unknown"},
            {"production_recommendations": "ENABLED"},
            {"status": "READY"},
            {"requested_markets": ["h2h", "spreads", "totals"]},
            {"missing_markets": []},
            {"market": "spreads"},
            {"handicap_and_totals_verified": True},
            {"raw_bookmaker_quotes_redistributed": True},
            {"raw_bookmaker_names_redistributed": True},
            {"model_value_advantage_verified": True},
            {"event_count": 3},
            {"event_count": True},
            {"events": None},
            {"as_of_utc": "2026-11-02T02:02:25"},
            {"as_of_utc": "invalid"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                output = audit(snapshot(**mutation), summary())
                self.assertEqual(output["status"], "HOLD")
                self.assertIsNone(output["as_of_utc"])
                self.assertFalse(output["market_coverage_complete"])
                self.assertFalse(output["handicap_available"])
                self.assertFalse(output["totals_available"])
                self.assertEqual(output["production_recommendations"], "DISABLED")

    def test_unverified_summary_never_authenticates_observed_h2h(self):
        for mutation in (
            {"schema": "unknown"},
            {"production_recommendations": "ENABLED"},
            {"raw_prices_or_bookmakers_included": True},
            {"quotes_are_executable": True},
            {"verified_bets": 5},
            {"verified_bets": False},
            {"captured_utc": "naive"},
        ):
            with self.subTest(mutation=mutation):
                output = audit(snapshot(), summary(**mutation))
                self.assertEqual(output["status"], "HOLD")
                self.assertEqual(output["public_h2h_consensus_event_count"], 0)
                self.assertEqual(output["missing_markets"], ["h2h", "spreads", "totals"])

    def test_requested_absent_is_not_observed(self):
        output = audit(snapshot(), summary(requested_markets=[]))
        self.assertEqual(output["status"], "HOLD")
        self.assertEqual(output["public_consensus_observed_markets"], [])

    def test_duplicate_unknown_and_malformed_requested_markets_rejected(self):
        for value in ("h2h", ["h2h", "h2h"], ["h2h", "unknown"],
                      [True], [["h2h"]], None):
            with self.subTest(requested=value):
                with self.assertRaises(ValueError):
                    audit(snapshot(), summary(requested_markets=value))

    def test_malformed_snapshot_scope_stays_hold(self):
        for value in ("h2h", ["h2h", "h2h"], [["h2h"]], [True], None):
            with self.subTest(scope=value):
                output = audit(snapshot(requested_markets=value), summary())
                self.assertEqual(output["status"], "HOLD")

    def test_checked_in_public_artifacts_never_claim_asian_quote_coverage(self):
        """Run on the actual repository files: no synthetic AH/OU evidence."""
        import json
        root = Path(__file__).resolve().parents[2]
        public = json.loads((root / "market" / "latest.json").read_text(encoding="utf-8"))
        private = json.loads((root / "market" / "private_summary_latest.json").read_text(encoding="utf-8"))
        output = audit(public, private)
        self.assertEqual(output["production_recommendations"], "DISABLED")
        self.assertFalse(output["market_coverage_complete"])
        self.assertFalse(output["handicap_available"])
        self.assertFalse(output["totals_available"])
        self.assertFalse(output["raw_prices_verified"])
        self.assertIn("spreads", output["missing_markets"])
        self.assertIn("totals", output["missing_markets"])
        # Counts of 1X2 consensus events cannot be reused as quoted Asian lines.
        self.assertEqual(output["public_h2h_consensus_event_count"],
                         public["event_count"] if output["status"] == "RESEARCH_ONLY" else 0)

    def test_invalid_container_input_is_rejected(self):
        for bad in (None, [], "text"):
            with self.assertRaises(ValueError):
                audit(bad, summary())
            with self.assertRaises(ValueError):
                audit(snapshot(), bad)


if __name__ == "__main__":
    unittest.main()
