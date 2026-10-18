"""Regression checks for user-selected 5% research EV threshold and quote age.

No synthetic quote or caller-provided probability can authenticate a bet.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from value_ev_policy import evaluate
from market_quote_gate import extract


class ValueFivePercentGateTests(unittest.TestCase):
    def test_five_percent_threshold_boundary_is_research_only(self):
        below = evaluate(.65, 2.0, conservative_probability=.524,
                         quote_age_seconds=20, minimum_conservative_ev=.05)
        self.assertEqual(below["reason"], "INSUFFICIENT_CONSERVATIVE_EV")
        self.assertFalse(below["research_value_screen_pass"])
        at = evaluate(.65, 2.0, conservative_probability=.525,
                      quote_age_seconds=20, minimum_conservative_ev=.05)
        self.assertTrue(at["research_value_screen_pass"])
        self.assertEqual(at["status"], "RESEARCH_ONLY")
        self.assertFalse(at["qualifies_for_recommendation"])
        self.assertEqual(at["production_recommendations"], "DISABLED")

    def test_ev_rounding_cannot_promote_subthreshold_candidate(self):
        # True EV is just below +5%, though its 8-decimal display rounds to 0.05.
        below = evaluate(.65, 2.0, conservative_probability=.524999999,
                         quote_age_seconds=20, minimum_conservative_ev=.05)
        self.assertEqual(below["conservative_ev"], .05)
        self.assertEqual(below["reason"], "INSUFFICIENT_CONSERVATIVE_EV")
        self.assertFalse(below["research_value_screen_pass"])

    def test_stale_and_missing_quote_age_cannot_pass(self):
        for age in (None, 121, -1):
            with self.subTest(age=age):
                result = evaluate(.7, 2.0, conservative_probability=.6,
                                  quote_age_seconds=age,
                                  minimum_conservative_ev=.05)
                self.assertEqual(result["reason"], "MISSING_OR_STALE_QUOTE")
                self.assertFalse(result["research_value_screen_pass"])

    def test_market_quote_age_and_match_identity_fail_closed(self):
        event = [{
            "id": "test-fixture", "sport_key": "soccer_epl",
            "commence_time": "2026-10-20T18:00:00Z",
            "home_team": "Home", "away_team": "Away",
            "bookmakers": [{"key": "book", "markets": [{
                "key": "spreads", "last_update": "2026-10-20T11:57:59Z",
                "outcomes": [{"name": "Away", "point": -2.75, "price": 2.0}]
            }]}]
        }]
        args = dict(captured_utc="2026-10-20T12:00:00Z",
                    league="soccer_epl", home="Home", away="Away")
        stale = extract(event, **args)
        self.assertEqual(stale["status"], "HOLD")
        self.assertEqual(stale["reject_reasons"]["STALE_OR_FUTURE_MARKET"], 1)
        event[0]["bookmakers"][0]["markets"][0]["last_update"] = "2026-10-20T11:59:30Z"
        matched = extract(event, **args)
        self.assertEqual(matched["quotes_accepted"], 1)
        self.assertFalse(matched["executable_bookmaker_price_verified"])
        mismatch = extract(event, **{**args, "away": "Other"})
        self.assertEqual(mismatch["status"], "HOLD")
        self.assertEqual(mismatch["quotes_accepted"], 0)


if __name__ == "__main__":
    unittest.main()
