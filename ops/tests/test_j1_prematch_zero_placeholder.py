"""Regression cases for pre-match 0-0 placeholders (synthetic, no network).

Motivated by the 2026-11-21 Kyoto–Urawa club page displaying '試合前'
alongside a 0-0 placeholder. No live score or outcome is claimed here.
"""
import unittest

from live_score_identity_guard import check


FIXTURE = {
    "gender": "men",
    "league": "j1",
    "home_id": "kyoto-sanga",
    "away_id": "urawa-reds",
    "kickoff_utc": "2026-11-21T05:00:00Z",
    "expected_identity_sealed_utc": "2026-11-21T04:00:00Z",
    "provider_event_ids": {
        "fotmob": "synthetic-kyoto-urawa-a",
        "sofascore": "synthetic-kyoto-urawa-b",
    },
    "provider_event_urls": {
        "fotmob": "https://www.fotmob.com/matches/synthetic-kyoto-urawa/a",
        "sofascore": "https://www.sofascore.com/football/match/synthetic-kyoto-urawa/b",
    },
}


def observations():
    rows = []
    for provider, event_id in FIXTURE["provider_event_ids"].items():
        rows.append({
            "provider": provider,
            "source_event_id": event_id,
            "gender": FIXTURE["gender"],
            "league": FIXTURE["league"],
            "home_id": FIXTURE["home_id"],
            "away_id": FIXTURE["away_id"],
            "kickoff_utc": FIXTURE["kickoff_utc"],
            "source_url": FIXTURE["provider_event_urls"][provider],
            "captured_utc": "2026-11-21T05:03:00Z",
            "source_updated_utc": "2026-11-21T05:02:00Z",
            "match_status": "NOT_STARTED",
            "score_home": 0,
            "score_away": 0,
        })
    return rows


class PrematchZeroPlaceholderTests(unittest.TestCase):
    def test_two_prematch_zero_placeholders_are_not_live_or_settlement(self):
        result = check(FIXTURE, observations(), "2026-11-21T05:04:00Z")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "PREMATCH_NOT_LIVE")
        self.assertEqual(result["match_status"], "NOT_STARTED")
        self.assertNotIn("score_home", result)
        self.assertNotIn("score_away", result)
        self.assertFalse(result["model_scoring_eligible"])
        self.assertFalse(result["settlement_certified"])
        self.assertFalse(result["price_or_positive_ev_certified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_prematch_vs_live_zero_zero_status_conflict_fails_closed(self):
        rows = observations()
        rows[1]["match_status"] = "FIRST_HALF"
        result = check(FIXTURE, rows, "2026-11-21T05:04:00Z")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "CROSS_SOURCE_SCORE_OR_STATUS_CONFLICT")
        self.assertFalse(result["model_scoring_eligible"])

    def test_raw_japanese_prematch_label_is_not_treated_as_live(self):
        rows = observations()
        rows[0]["match_status"] = "試合前"
        result = check(FIXTURE, rows, "2026-11-21T05:04:00Z")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "INVALID_STATUS")
        self.assertFalse(result["model_scoring_eligible"])
        self.assertFalse(result["settlement_certified"])

    def test_prematch_zero_placeholder_goes_stale_after_ten_minutes(self):
        rows = observations()
        for row in rows:
            row["captured_utc"] = "2026-11-21T05:10:00Z"
            row["source_updated_utc"] = "2026-11-21T05:10:00Z"
        result = check(FIXTURE, rows, "2026-11-21T05:11:00Z")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "STALE_PREMATCH_STATUS")

    def test_prematch_label_with_scored_goal_fails_closed(self):
        rows = observations()
        rows[0]["score_home"] = 1
        result = check(FIXTURE, rows, "2026-11-21T05:04:00Z")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "PREMATCH_WITH_GOALS")


if __name__ == "__main__":
    unittest.main()
