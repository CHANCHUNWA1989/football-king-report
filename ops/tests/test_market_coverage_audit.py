import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_coverage_audit import audit


def market_h2h():
    # A public no-vig consensus snapshot is not a raw executable market price.
    return {
        "status": "RESEARCH_ONLY",
        "market": "h2h",
        "as_of_utc": "2026-11-06T14:15:00Z",
        "event_count": 1,
        "events": [{"source_event_id": "synthetic-1", "p_home": 0.5,
                    "p_draw": 0.3, "p_away": 0.2}],
        "production_recommendations": "DISABLED",
    }


class MarketCoverageAuditTests(unittest.TestCase):
    def test_duplicate_native_event_ids_cannot_establish_h2h_coverage(self):
        for probabilities in ((.5, .3, .2), (.4, .3, .3)):
            with self.subTest(probabilities=probabilities):
                snapshot = market_h2h()
                snapshot["events"].append({
                    "source_event_id": "synthetic-1",
                    "p_home": probabilities[0], "p_draw": probabilities[1],
                    "p_away": probabilities[2],
                })
                snapshot["event_count"] = 2
                result = audit(snapshot, {"requested_markets": ["h2h"]})
                self.assertEqual(result["observed_consensus_markets"], [])
                self.assertEqual(result["requested_but_unobserved"], ["h2h"])
                self.assertEqual(result["missing_markets"], ["h2h", "spreads", "totals"])
                self.assertFalse(result["market_coverage_complete"])
                self.assertFalse(result["raw_prices_verified"])
                self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_distinct_native_event_ids_preserve_consensus_only_coverage(self):
        snapshot = market_h2h()
        snapshot["events"].append({**snapshot["events"][0],
                                   "source_event_id": "synthetic-2"})
        snapshot["event_count"] = 2
        result = audit(snapshot, {"requested_markets": ["h2h", "spreads", "totals"]})
        self.assertEqual(result["observed_consensus_markets"], ["h2h"])
        self.assertEqual(result["missing_markets"], ["spreads", "totals"])
        self.assertEqual([row["source_event_id"] for row in snapshot["events"]],
                         ["synthetic-1", "synthetic-2"])
        self.assertFalse(result["market_coverage_complete"])
        self.assertFalse(result["raw_prices_verified"])
        self.assertFalse(result["can_recommend_handicap_or_totals"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_real_h2h_consensus_does_not_authenticate_other_markets(self):
        result = audit(market_h2h(), {"requested_markets": ["h2h"]})
        self.assertEqual(result["observed_consensus_markets"], ["h2h"])
        self.assertEqual(result["missing_markets"], ["spreads", "totals"])
        self.assertFalse(result["market_coverage_complete"])
        self.assertFalse(result["can_recommend_handicap_or_totals"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_requested_three_markets_is_not_evidence_of_collection(self):
        result = audit(market_h2h(), {
            "requested_markets": ["h2h", "spreads", "totals"],
            "coverage": [{"league": "epl", "quotes": 999}],
        })
        self.assertEqual(result["requested_markets"], ["h2h", "spreads", "totals"])
        self.assertEqual(result["requested_but_unobserved"], ["spreads", "totals"])
        self.assertFalse(result["handicap_available"])
        self.assertFalse(result["totals_available"])
        self.assertFalse(result["market_coverage_complete"])

    def test_empty_snapshot_cannot_claim_even_h2h_observation(self):
        result = audit({}, {"requested_markets": ["h2h", "spreads", "totals"]})
        self.assertEqual(result["observed_consensus_markets"], [])
        self.assertEqual(result["missing_markets"], ["h2h", "spreads", "totals"])
        self.assertFalse(result["market_coverage_complete"])

    def test_bad_or_inconsistent_public_snapshot_fails_closed(self):
        for snapshot in (
            {"market": "h2h", "status": "RESEARCH_ONLY", "event_count": 1, "events": []},
            {"market": "h2h", "status": "RESEARCH_ONLY", "event_count": True,
             "events": [{}]},
            {"market": "spreads", "status": "RESEARCH_ONLY", "event_count": 1,
             "events": [{}]},
            {"market": "h2h", "status": "RESEARCH_ONLY", "event_count": 1,
             "events": [{}], "production_recommendations": "ENABLED"},
        ):
            with self.subTest(snapshot=snapshot):
                result = audit(snapshot, {"requested_markets": ["h2h", "spreads", "totals"]})
                self.assertEqual(result["observed_consensus_markets"], [])
                self.assertFalse(result["market_coverage_complete"])

    def test_bad_requested_market_list_rejected(self):
        for requested in ("h2h", ["h2h", "h2h"], ["h2h", "corners"],
                          [None], [True], ["h2h", 3]):
            with self.subTest(requested=requested), self.assertRaises(ValueError):
                audit({}, {"requested_markets": requested})

    def test_h2h_consensus_does_not_prove_executable_prices(self):
        result = audit(market_h2h(), {
            "requested_markets": ["h2h", "spreads", "totals"],
            "quotes_are_executable": True, "raw_prices_verified": True,
        })
        self.assertFalse(result["raw_prices_verified"])
        self.assertFalse(result["market_coverage_complete"])
        self.assertFalse(result["can_recommend_handicap_or_totals"])
        self.assertEqual(result["reason"], "MARKET_LEVEL_RAW_QUOTES_NOT_INDEPENDENTLY_VERIFIED")


if __name__ == "__main__":
    unittest.main()
