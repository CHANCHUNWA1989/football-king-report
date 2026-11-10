"""End-to-end bookmaker collector adversarial data tests, offline only."""
import copy
import unittest
from unittest.mock import patch

from ops.odds_market import collect
from ops.tests.test_european_market_stress import NOW, fixture


def simulate(matches):
    def fake_retrieve(path, key, **kwargs):
        if path == "/sports/":
            return [{"key": "soccer_epl", "active": True}], {
                "used": 0, "remaining": 500, "last": 0}
        if path == "/sports/soccer_epl/odds/":
            return matches, {"used": 1, "remaining": 499, "last": 1}
        raise AssertionError("Unexpected paid request")
    with patch("ops.odds_market.retrieve", side_effect=fake_retrieve):
        return collect("dummy-key", now=NOW)


class TestEuropeanCollectorIntegrity(unittest.TestCase):
    def test_wrong_sport_key_cannot_pollute_league(self):
        event = fixture()
        event["sport_key"] = "soccer_spain_la_liga"
        report = simulate([event])
        self.assertEqual(report["event_count"], 0)
        self.assertEqual(report["status"], "HOLD")

    def test_valid_event_is_research_only_never_betting(self):
        event = fixture()
        event["sport_key"] = "soccer_epl"
        report = simulate([event])
        self.assertEqual(report["event_count"], 1)
        self.assertEqual(report["status"], "RESEARCH_ONLY")
        self.assertFalse(report["events"][0]["prediction_or_value_bet"])
        self.assertFalse(report["model_value_advantage_verified"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_duplicate_event_excludes_both_copies_preserves_other_event(self):
        a = fixture()
        a["sport_key"] = "soccer_epl"
        b = copy.deepcopy(a)
        b["id"] = "fixture-2"
        report = simulate([a, copy.deepcopy(a), b])
        self.assertEqual(report["event_count"], 1)
        self.assertEqual(report["events"][0]["source_event_id"], "fixture-2")


if __name__ == "__main__":
    unittest.main()
