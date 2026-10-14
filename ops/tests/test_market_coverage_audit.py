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
        self.assertTrue(result["market_coverage_complete"])
        self.assertFalse(result["raw_prices_verified"])
        self.assertFalse(result["can_recommend_handicap_or_totals"])

    def test_bad_market_list_rejected(self):
        with self.assertRaises(ValueError):
            audit({}, {"requested_markets": "h2h"})


if __name__ == "__main__":
    unittest.main()
