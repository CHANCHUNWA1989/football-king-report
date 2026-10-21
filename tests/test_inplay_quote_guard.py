"""Regression tests for fail-closed in-play quote provenance."""
import unittest
from ops.inplay_quote_guard import validate_inplay_quote

NOW = "2026-10-21T03:45:00Z"

def sample():
    return dict(match_id="match-123", source="licensed-provider",
                settlement_basis="FULL_MATCH", minute=32,
                home_goals=0, away_goals=1,
                provider_updated_utc="2026-10-21T03:44:20Z",
                captured_utc="2026-10-21T03:44:35Z")

class QuoteGuardTests(unittest.TestCase):
    def test_fresh_full_match(self):
        r = validate_inplay_quote(sample(), decision_utc=NOW)
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertEqual(r["settlement_basis"], "FULL_MATCH")

    def test_remainder_requires_explicit_basis(self):
        q = sample()
        q["settlement_basis"] = "REMAINDER"
        self.assertEqual(validate_inplay_quote(q, decision_utc=NOW)["settlement_basis"], "REMAINDER")
        q["settlement_basis"] = None
        with self.assertRaises(ValueError):
            validate_inplay_quote(q, decision_utc=NOW)

    def test_stale_and_future(self):
        q = sample()
        q["provider_updated_utc"] = "2026-10-21T03:42:00Z"
        with self.assertRaises(ValueError):
            validate_inplay_quote(q, decision_utc=NOW)
        q = sample()
        q["captured_utc"] = "2026-10-21T03:46:00Z"
        with self.assertRaises(ValueError):
            validate_inplay_quote(q, decision_utc=NOW)

    def test_missing_identity_and_naive_time(self):
        q = sample()
        q["match_id"] = ""
        with self.assertRaises(ValueError):
            validate_inplay_quote(q, decision_utc=NOW)
        q = sample()
        q["captured_utc"] = "2026-10-21T03:44:35"
        with self.assertRaises(ValueError):
            validate_inplay_quote(q, decision_utc=NOW)

    def test_invalid_scores(self):
        q = sample()
        q["home_goals"] = -1
        with self.assertRaises(ValueError):
            validate_inplay_quote(q, decision_utc=NOW)

if __name__ == "__main__":
    unittest.main()
