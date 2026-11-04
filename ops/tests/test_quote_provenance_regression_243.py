"""Regression tests: quote provenance must not be confused with executable prices."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_quote_gate import extract

CAPTURE = "2026-10-17T00:00:00Z"


def fixture():
    return [{
        "id": "verified-event-id", "sport_key": "soccer_germany_bundesliga",
        "commence_time": "2026-10-17T01:00:00Z",
        "home_team": "Frankfurt", "away_team": "Cologne",
        "bookmakers": [{
            "key": "example",
            "markets": [{
                "key": "spreads", "last_update": "2026-10-16T23:59:30Z",
                "outcomes": [
                    {"name": "Cologne", "point": 0.75, "price": 1.95},
                    {"name": "Frankfurt", "point": -0.75, "price": 1.85},
                ],
            }],
        }],
    }]


def check(payload):
    return extract(payload, captured_utc=CAPTURE,
                   league="soccer_germany_bundesliga",
                   home="Frankfurt", away="Cologne")


class QuoteProvenanceRegression(unittest.TestCase):
    def test_fresh_quote_is_research_only(self):
        result = check(fixture())
        self.assertEqual(result["quotes_accepted"], 2)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["executable_bookmaker_price_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertIsNone(result["recommendation"])

    def test_stale_market_fails_closed(self):
        payload = fixture()
        payload[0]["bookmakers"][0]["markets"][0]["last_update"] = "2026-10-16T23:40:00Z"
        result = check(payload)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["quotes_accepted"], 0)
        self.assertEqual(result["reject_reasons"]["STALE_OR_FUTURE_MARKET"], 1)

    def test_wrong_fixture_fails_closed(self):
        payload = fixture()
        payload[0]["id"] = "another-fixture"
        payload[0]["home_team"] = "Different team"
        result = check(payload)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["quotes_accepted"], 0)

    def test_wrong_market_line_is_not_accepted_as_requested_line(self):
        payload = fixture()
        payload[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["point"] = 0.5
        result = check(payload)
        cologne = [q for q in result["quotes"] if q["outcome"] == "Cologne"]
        self.assertEqual(len(cologne), 1)
        self.assertNotEqual(cologne[0]["point"], 0.75)
        self.assertFalse(result["executable_bookmaker_price_verified"])


if __name__ == "__main__":
    unittest.main()
