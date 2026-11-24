"""Independent monitor must not accept contradictory market availability."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watchdog import evaluate_market_layer


class MarketStateConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 24, 11, tzinfo=timezone.utc)
        self.market = {
            "status": "RESEARCH_ONLY", "source_state": "RESEARCH_ONLY",
            "market_as_of_utc": (self.now - timedelta(hours=1)).isoformat(),
            "model_events": 1, "market_events": 1, "matched_count": 1,
            "production_recommendations": "DISABLED",
        }
        self.pairs = {"status": "RESEARCH_ONLY", "matched_count": 1,
                      "comparisons": [{}], "production_recommendations": "DISABLED"}

    def errors(self):
        return evaluate_market_layer(self.market, self.pairs, now=self.now)

    def test_valid_available_source(self):
        self.assertEqual(self.errors(), [])

    def test_hold_source_cannot_have_matched_pairs(self):
        self.market["source_state"] = "HOLD"
        self.assertIn("MARKET_SOURCE_NOT_READY_FOR_PAIRS", self.errors())

    def test_missing_or_unknown_source_state(self):
        for state in (None, "READY", True, []):
            with self.subTest(state=state):
                self.market["source_state"] = state
                self.assertIn("INVALID_MARKET_SOURCE_STATE", self.errors())

    def test_hold_pair_status_cannot_have_positive_pair_count(self):
        self.market["status"] = self.pairs["status"] = "HOLD"
        self.assertIn("HOLD_MARKET_HAS_PAIRS", self.errors())

    def test_missing_comparisons_with_nonzero_count(self):
        del self.pairs["comparisons"]
        self.assertIn("PUBLIC_MARKET_PAIR_COUNT_MISMATCH", self.errors())

    def test_hold_source_without_pairs_is_not_false_ready(self):
        self.market.update(status="HOLD", source_state="HOLD", matched_count=0,
                           market_events=0, market_as_of_utc=None)
        self.pairs.update(status="HOLD", matched_count=0, comparisons=[])
        self.assertEqual(self.errors(), [])

    def test_stale_source_alert_is_not_suppressed_by_collection_hold(self):
        self.market.update(status="HOLD", matched_count=0,
                           market_as_of_utc=(self.now-timedelta(hours=96)).isoformat(),
                           last_collection_state="HOLD", last_collection_reason="FREE_QUOTA_GUARD")
        self.pairs.update(status="HOLD", matched_count=0, comparisons=[])
        self.assertIn("DERIVED_MARKET_DATA_STALE", self.errors())


if __name__ == "__main__":
    unittest.main()
