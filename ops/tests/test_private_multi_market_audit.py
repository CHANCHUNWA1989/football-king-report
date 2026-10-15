import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_multi_market_audit import audit


class PrivateMultiMarketAuditTests(unittest.TestCase):
    def setUp(self):
        self.captured = "2026-10-15T12:00:00Z"
        self.event = {
            "id": "stable-1", "sport_key": "soccer_epl",
            "home_team": "Home", "away_team": "Away",
            "commence_time": "2026-10-15T16:00:00Z",
            "bookmakers": [{
                "key": "example-book",
                "markets": [
                    {"key": "h2h", "last_update": self.captured,
                     "outcomes": [{"name": "Home", "price": 2.1}]},
                    {"key": "totals", "last_update": self.captured,
                     "outcomes": [{"name": "Over", "point": 2.5, "price": 1.9}]},
                    {"key": "spreads", "last_update": self.captured,
                     "outcomes": [{"name": "Away", "point": 0.25, "price": 1.95}]},
                ],
            }],
        }

    def test_three_markets_observed_without_exposing_prices(self):
        result = audit([self.event], self.captured)
        self.assertEqual(result["missing_markets"], ["h2h", "spreads", "totals"])
        self.assertEqual(result["rejections"]["INCOMPLETE_MARKET_SIDES"], 3)
        self.assertEqual(result["complete_prematch_bookmaker_lines_by_market"],
                         {"h2h": 0, "spreads": 0, "totals": 0})
        self.assertNotIn("1.95", str(result))
        self.assertNotIn("example-book", str(result))
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_complete_two_sided_lines_are_counted(self):
        markets = self.event["bookmakers"][0]["markets"]
        markets[0]["outcomes"] += [
            {"name": "Draw", "price": 3.1},
            {"name": "Away", "price": 3.2},
        ]
        markets[1]["outcomes"].append(
            {"name": "Under", "point": 2.5, "price": 1.9})
        markets[2]["outcomes"].append(
            {"name": "Home", "point": -0.25, "price": 1.95})
        result = audit([self.event], self.captured)
        self.assertEqual(result["missing_markets"], [])
        self.assertEqual(result["complete_prematch_bookmaker_lines_by_market"],
                         {"h2h": 1, "spreads": 1, "totals": 1})

    def test_stale_quotes_do_not_count(self):
        self.event["bookmakers"][0]["markets"][0]["last_update"] = "2026-10-15T11:00:00Z"
        result = audit([self.event], self.captured)
        self.assertIn("h2h", result["missing_markets"])

    def test_missing_identity_fails_closed(self):
        del self.event["id"]
        result = audit([self.event], self.captured)
        self.assertEqual(result["status"], "HOLD")

    def test_duplicate_event_ids_quarantine_all_copies(self):
        import copy
        result = audit([self.event, copy.deepcopy(self.event)], self.captured)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["events_matched"], 0)
        self.assertEqual(result["rejections"]["DUPLICATE_EVENT_ID"], 2)
        self.assertEqual(result["missing_markets"], ["h2h", "spreads", "totals"])

    def test_empty_input_holds(self):
        result = audit([], self.captured)
        self.assertEqual(result["missing_markets"], ["h2h", "spreads", "totals"])
        self.assertEqual(result["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
