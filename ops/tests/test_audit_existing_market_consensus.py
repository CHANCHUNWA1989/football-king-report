import unittest
from ops.audit_existing_market_consensus import inspect_market


def market():
    return {
        "status": "RESEARCH_ONLY",
        "as_of_utc": "2026-11-06T02:00:00Z",
        "requested_markets": ["h2h"], "missing_markets": ["spreads", "totals"],
        "events": [{
            "source_event_id": "id1", "league": "epl",
            "kickoff_utc": "2026-11-06T20:00:00Z",
            "market_last_update_utc": "2026-11-06T01:45:00Z",
            "p_home": 0.5, "p_draw": 0.3, "p_away": 0.2,
            "probabilities_are_no_vig_consensus": True,
        }],
    }


class MarketConsensusAuditTests(unittest.TestCase):
    def test_consensus_never_promoted_to_executable_odds(self):
        r = inspect_market(market())
        self.assertEqual(r["valid_1x2_consensus_events"], 1)
        self.assertEqual(r["missing_fields_per_valid_event"]["executable_bookmaker_odds"], 1)
        self.assertFalse(r["asian_ev_calculable"])
        self.assertFalse(r["executable_1x2_ev_calculable"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_duplicate_excluded(self):
        d = market()
        d["events"].append(dict(d["events"][0]))
        self.assertEqual(inspect_market(d)["valid_1x2_consensus_events"], 1)

    def test_post_kickoff_market_excluded(self):
        d = market()
        d["events"][0]["market_last_update_utc"] = "2026-11-07T10:00:00Z"
        self.assertEqual(inspect_market(d)["valid_1x2_consensus_events"], 0)

    def test_update_after_snapshot_excluded(self):
        d = market()
        d["events"][0]["market_last_update_utc"] = "2026-11-06T02:00:01Z"
        r = inspect_market(d)
        self.assertEqual(r["valid_1x2_consensus_events"], 0)
        self.assertEqual(r["missing_fields_per_valid_event"]["invalid_consensus_or_time"], 1)

    def test_snapshot_at_kickoff_excluded(self):
        d = market()
        d["as_of_utc"] = d["events"][0]["kickoff_utc"]
        self.assertEqual(inspect_market(d)["valid_1x2_consensus_events"], 0)

    def test_missing_naive_or_invalid_snapshot_rejected(self):
        for value in (None, "2026-11-06T02:00:00", "invalid", 123):
            d = market()
            d["as_of_utc"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                inspect_market(d)

    def test_equal_instant_in_different_timezones_is_valid(self):
        d = market()
        d["events"][0]["market_last_update_utc"] = "2026-11-06T10:00:00+08:00"
        r = inspect_market(d)
        self.assertEqual(r["valid_1x2_consensus_events"], 1)
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["asian_ev_calculable"])

    def test_bad_probabilities_excluded(self):
        d = market()
        d["events"][0]["p_home"] = 0.9
        self.assertEqual(inspect_market(d)["valid_1x2_consensus_events"], 0)

    def test_non_research_market_rejected(self):
        d = market()
        d["status"] = "READY"
        with self.assertRaises(ValueError):
            inspect_market(d)


if __name__ == "__main__":
    unittest.main()
