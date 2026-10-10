"""Additional quote-ingestion regressions for stable fixture and provider identities."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_quote_gate import extract


def event():
    return [{
        "id": "match-100", "sport_key": "soccer_epl",
        "home_team": "Home", "away_team": "Away",
        "commence_time": "2026-10-12T18:00:00Z",
        "bookmakers": [{
            "key": "book_a",
            "markets": [{
                "key": "h2h", "last_update": "2026-10-12T11:59:30Z",
                "outcomes": [{"name": "Home", "price": 2.1},
                             {"name": "Draw", "price": 3.2},
                             {"name": "Away", "price": 3.4}],
            }],
        }],
    }]


def run(rows):
    return extract(rows, captured_utc="2026-10-12T12:00:00Z",
                   league="soccer_epl", home="Home", away="Away")


class MarketIdentityHardeningTests(unittest.TestCase):
    def test_normal_fixture_unchanged(self):
        value = run(event())
        self.assertEqual(value["quotes_accepted"], 3)
        self.assertEqual(value["matched_events"], 1)
        self.assertEqual(value["quotes"][0]["event_id"], "match-100")
        self.assertEqual(value["production_recommendations"], "DISABLED")

    def test_missing_or_empty_event_id_never_accepted(self):
        for bad in (None, "", " ", 999, [], {}):
            with self.subTest(id=repr(bad)):
                payload = event()
                payload[0]["id"] = bad
                value = run(payload)
                self.assertEqual(value["status"], "HOLD")
                self.assertEqual(value["matched_events"], 0)
                self.assertEqual(value["quotes_accepted"], 0)
                self.assertEqual(value["reject_reasons"], {"INVALID_EVENT_ID": 1})

    def test_duplicate_event_cannot_inflate_quote_counts(self):
        item = event()[0]
        value = run([item, copy.deepcopy(item)])
        self.assertEqual(value["quotes_accepted"], 3)
        self.assertEqual(value["matched_events"], 1)
        self.assertEqual(value["reject_reasons"], {"DUPLICATE_EVENT_ID": 1})

    def test_bogus_bookmaker_key_rejected(self):
        for bad in ("", " ", "X"*129):
            with self.subTest(key=repr(bad)):
                payload = event()
                payload[0]["bookmakers"][0]["key"] = bad
                value = run(payload)
                self.assertEqual(value["status"], "HOLD")
                self.assertEqual(value["reject_reasons"], {"INVALID_BOOKMAKER": 1})

    def test_wrong_type_market_key_fails_closed_not_crash(self):
        for bad in ([], {}, 12, None):
            with self.subTest(key=repr(bad)):
                payload = event()
                payload[0]["bookmakers"][0]["markets"][0]["key"] = bad
                value = run(payload)
                self.assertEqual(value["status"], "HOLD")
                self.assertEqual(value["quotes_accepted"], 0)
                self.assertEqual(value["reject_reasons"], {"UNSUPPORTED_MARKET": 1})

    def test_unmatched_events_still_ignored(self):
        payload = event()
        payload[0]["home_team"] = "Not Home"
        self.assertEqual(run(payload)["matched_events"], 0)


if __name__ == "__main__":
    unittest.main()
