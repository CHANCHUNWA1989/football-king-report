import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_coverage_audit import audit


class MarketCoverageAuditTests(unittest.TestCase):
    def test_h2h_only_reports_missing_markets(self):
        result = audit({"as_of_utc": "2026-10-14T00:00:00Z"},
                       {"requested_markets": ["h2h"]})
        self.assertEqual(result["missing_markets"], ["spreads", "totals"])
        self.assertFalse(result["can_recommend_handicap_or_totals"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_all_markets_does_not_claim_verified_prices(self):
        result = audit({}, {"requested_markets": ["h2h", "spreads", "totals"]})
        self.assertTrue(result["requested_market_types_complete"])
        self.assertFalse(result["market_coverage_complete"])
        self.assertFalse(result["handicap_available"])
        self.assertFalse(result["totals_available"])
        self.assertEqual(result["markets_without_complete_line_evidence"], ["h2h", "spreads", "totals"])
        self.assertEqual(result["observed_complete_market_types"], [])
        self.assertFalse(result["raw_prices_verified"])
        self.assertFalse(result["can_recommend_handicap_or_totals"])

    def test_aggregate_counts_and_stale_h2h_do_not_prove_market_lines(self):
        result = audit(
            {"as_of_utc": "2026-11-20T08:24:35Z", "event_count": 108,
             "requested_markets": ["h2h"], "handicap_and_totals_verified": False},
            {"requested_markets": ["h2h", "spreads", "totals"],
             "input_status": "QUOTA_GUARD", "counts": {"RESEARCH_ONLY": 3681},
             "coverage": [{"league": "epl", "quotes": 3681, "status": "COUNTS_ONLY"}]})
        self.assertEqual(result["missing_markets"], [])
        self.assertEqual(result["missing_markets_scope"], "REQUESTED_MARKET_TYPES_ONLY")
        self.assertFalse(result["market_coverage_complete"])
        self.assertFalse(result["per_market_line_evidence_available"])
        self.assertFalse(result["handicap_available"])
        self.assertFalse(result["totals_available"])
        self.assertEqual(result["reason"], "REQUESTED_TYPES_NOT_LINE_EVIDENCE")
        self.assertFalse(result["can_recommend_handicap_or_totals"])

    def test_bad_market_list_rejected(self):
        with self.assertRaises(ValueError):
            audit({}, {"requested_markets": "h2h"})


if __name__ == "__main__":
    unittest.main()

