import copy
import unittest
from datetime import datetime, timedelta, timezone
from ops.private_summary_archive import prepare, check
from ops.private_artifact_guard import sanitize

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)

def fixture(at=None):
    stamp = (at or NOW).isoformat()
    result = sanitize({
        "input_status": "CONNECTED",
        "generated_utc": stamp,
        "counts": {"RESEARCH_ONLY": 3837, "VERIFIED_VALUE": 500},
        "coverage": [{"league": "epl", "quotes": 50,
                      "bookmaker": "never-publish-me",
                      "decimal_odds": 2.4, "home": "Never-publish-home"}],
        "requested_markets": ["h2h"],
        "candidates": [{"fixture_id": "secret-123", "decimal_odds": 2.7}]},
        {"grounded_progress": {"settled_cases_in_archive": 1}})
    return result

class PrivateSummaryArchiveTests(unittest.TestCase):
    def test_sanitized_quotes_are_archivable(self):
        data = fixture()
        self.assertEqual(check(data, NOW), NOW)
        self.assertEqual(data["counts"]["VERIFIED_VALUE"], 0)
        self.assertNotIn("never-publish-me", repr(data))
        merged, changed = prepare(None, data, NOW)
        self.assertTrue(changed)
        self.assertEqual(merged["counts"]["RESEARCH_ONLY"], 3837)

    def test_old_report_cannot_replace_new(self):
        new = fixture()
        old = fixture(NOW - timedelta(hours=2))
        same, changed = prepare(new, old, NOW)
        self.assertFalse(changed)
        self.assertEqual(same, new)
        newer, changed = prepare(old, new, NOW)
        self.assertTrue(changed)
        self.assertEqual(newer, new)

    def test_injected_identifiers_fail_closed(self):
        d = fixture()
        for key, value in (("bookmaker", "secretbook"),
                           ("prices", [1.8]),
                           ("home", "Team A")):
            tampered = dict(d)
            tampered[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "UNAPPROVED_PUBLIC_FIELDS"):
                check(tampered, NOW)

    def test_forged_certification_and_raw_odds_rejected(self):
        for key, value in (("verified_bets", 5),
                           ("raw_prices_or_bookmakers_included", True),
                           ("quotes_are_executable", True),
                           ("production_recommendations", "ENABLED")):
            tampered = fixture()
            tampered[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                check(tampered, NOW)

    def test_stale_and_future_rejected(self):
        for day in (-40, 1):
            with self.subTest(day=day), self.assertRaises(ValueError):
                check(fixture(NOW + timedelta(days=day)), NOW)

    def test_bad_collection_fails(self):
        d=fixture()
        d["coverage"][0]["away"]="Secret Away"
        with self.assertRaises(ValueError):
            check(d,NOW)

if __name__ == "__main__":
    unittest.main()
