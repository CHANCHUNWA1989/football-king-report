"""Synthetic same-publisher alias regression tests; offline, no actual score."""
import copy
import unittest

from jleague_alias_consensus_guard import triage_aliases


FIXTURE_ID = "2026112108"
PUBLISHER = "kyoto_sanga_official"
HOST = "www.sanga-fc.jp"
NOW = "2026-11-21T05:47:00Z"


def aliases():
    common = {
        "publisher": PUBLISHER,
        "fixture_id": FIXTURE_ID,
        "raw_status": "試合中",
        "home_goals": 0,
        "away_goals": 1,
        "captured_utc": "2026-11-21T05:46:00Z",
        "source_updated_utc": "2026-11-21T05:45:00Z",
    }
    return [
        {**common, "source_url": "https://www.sanga-fc.jp/game/data/2026112108"},
        {**common, "source_url": "https://www.sanga-fc.jp/index.php/game/data/2026112108"},
    ]


class SamePublisherAliasTests(unittest.TestCase):
    def run_gate(self, items=None):
        return triage_aliases(items if items is not None else aliases(),
                              fixture_id=FIXTURE_ID, publisher=PUBLISHER,
                              host=HOST, as_of_utc=NOW)

    def assert_holds_without_score(self, result):
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["can_count_as_two_sources"])
        self.assertFalse(result["model_scoring_eligible"])
        self.assertFalse(result["settlement_certified"])
        self.assertFalse(result["positive_ev_certified"])
        self.assertFalse(result["independently_authenticated"])
        self.assertNotIn("home_goals", result)
        self.assertNotIn("away_goals", result)

    def test_conflicting_old_prematch_zero_and_new_live_goal_quarantined(self):
        items = aliases()
        items[1]["raw_status"] = "試合前"
        items[1]["away_goals"] = 0
        result = self.run_gate(items)
        self.assert_holds_without_score(result)
        self.assertEqual(result["reason"], "SAME_PUBLISHER_ALIAS_CONFLICT")

    def test_matching_0_1_aliases_still_not_two_sources(self):
        result = self.run_gate()
        self.assert_holds_without_score(result)
        self.assertEqual(result["reason"], "SAME_PUBLISHER_NOT_INDEPENDENT")

    def test_two_matching_prematch_zero_placeholders_not_independent(self):
        items = aliases()
        for item in items:
            item["raw_status"] = "試合前"
            item["away_goals"] = 0
        self.assert_holds_without_score(self.run_gate(items))

    def test_wrong_fixture_id_rejected(self):
        items = aliases()
        items[1]["fixture_id"] = "some-other-match"
        result = self.run_gate(items)
        self.assert_holds_without_score(result)
        self.assertEqual(result["reason"], "FIXTURE_IDENTITY_CONFLICT")

    def test_different_provider_cannot_pose_as_alias(self):
        items = aliases()
        items[1]["publisher"] = "another-provider"
        result = self.run_gate(items)
        self.assert_holds_without_score(result)
        self.assertEqual(result["reason"], "NOT_SAME_EXPECTED_PUBLISHER")

    def test_old_alias_cannot_be_refreshed_by_scraping_again(self):
        items = aliases()
        items[1]["source_updated_utc"] = "2026-11-21T05:30:00Z"
        result = self.run_gate(items)
        self.assert_holds_without_score(result)
        self.assertEqual(result["reason"], "STALE_OR_FUTURE_ALIAS")

    def test_duplicate_url_is_not_an_independent_alias(self):
        items = aliases()
        items[1]["source_url"] = items[0]["source_url"]
        result = self.run_gate(items)
        self.assert_holds_without_score(result)
        self.assertEqual(result["reason"], "DUPLICATE_URL_NOT_ALIASES")

    def test_spoofed_sibling_domain_rejected(self):
        items = aliases()
        items[1]["source_url"] = "https://www.sanga-fc.jp.attacker.example/game/data/2026112108"
        result = self.run_gate(items)
        self.assert_holds_without_score(result)
        self.assertEqual(result["reason"], "INVALID_ALIAS_URL")

    def test_different_fixture_url_rejected_even_if_declared_id_matches(self):
        items = aliases()
        items[1]["source_url"] = (
            "https://www.sanga-fc.jp/index.php/game/data/2026112109"
        )
        result = self.run_gate(items)
        self.assert_holds_without_score(result)
        self.assertEqual(result["reason"], "ALIAS_URL_NOT_BOUND_TO_FIXTURE")

    def test_unrelated_page_on_official_hostname_rejected(self):
        items = aliases()
        items[1]["source_url"] = (
            "https://www.sanga-fc.jp/news/detail/2026112108"
        )
        result = self.run_gate(items)
        self.assert_holds_without_score(result)
        self.assertEqual(result["reason"], "ALIAS_URL_NOT_BOUND_TO_FIXTURE")

    def test_invalid_expected_fixture_id_fails_closed(self):
        result = triage_aliases(
            aliases(), fixture_id="../2026112108", publisher=PUBLISHER,
            host=HOST, as_of_utc=NOW,
        )
        self.assert_holds_without_score(result)
        self.assertEqual(result["reason"], "MISSING_EXPECTED_IDENTITY")

    def test_missing_upstream_timestamp_fails_closed(self):
        items = aliases()
        items[0]["source_updated_utc"] = None
        result = self.run_gate(items)
        self.assert_holds_without_score(result)
        self.assertEqual(result["reason"], "MISSING_TIMESTAMP")


if __name__ == "__main__":
    unittest.main()
