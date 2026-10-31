"""Synthetic tests for live source identity and freshness (no network)."""
import copy
import unittest
from live_score_identity_guard import check

FIXTURE = {
    "gender": "men", "league": "epl", "home_id": "manchester-city",
    "away_id": "brighton", "kickoff_utc": "2026-10-31T15:00:00Z",
    "expected_identity_sealed_utc": "2026-10-31T14:00:00Z",
    "provider_event_ids": {"fotmob": "5795502", "skysports": "559531"},
    "provider_event_urls": {
        "fotmob": "https://www.fotmob.com/en-GB/matches/manchester-city-vs-brighton-hove-albion/2vnwg2",
        "skysports": "https://www.skysports.com/football/manchester-city-vs-brighton-and-hove-albion/live/559531",
    },
}


def source(provider="fotmob"):
    return {
        "provider": provider, "source_event_id": FIXTURE["provider_event_ids"][provider],
        "gender": "men", "league": "epl", "home_id": "manchester-city", "away_id": "brighton",
        "kickoff_utc": "2026-10-31T15:00:00Z",
        "source_url": FIXTURE["provider_event_urls"][provider],
        "captured_utc": "2026-10-31T15:50:00Z",
        "source_updated_utc": "2026-10-31T15:49:00Z",
        "match_status": "HALF_TIME", "score_home": 0, "score_away": 1,
    }


class LiveScoreIdentityGuardTests(unittest.TestCase):
    def observations(self):
        return [source(), source("skysports")]

    def run_guard(self, items=None, fixture=None, now="2026-10-31T15:51:00Z"):
        return check(fixture or FIXTURE, items if items is not None else self.observations(), now)

    def test_same_match_both_sources_still_not_certified_result(self):
        result = self.run_guard()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual([result["score_home"], result["score_away"]], [0, 1])
        self.assertFalse(result["independently_authenticated"])
        self.assertFalse(result["settlement_certified"])
        self.assertFalse(result["model_scoring_eligible"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_postkickoff_provider_id_backfill_is_blocked(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture["expected_identity_sealed_utc"] = "2026-10-31T15:30:00Z"
        self.assertEqual(self.run_guard(fixture=fixture)["reason"],
                         "EXPECTED_IDENTITY_NOT_SEALED_PREMATCH")

    def test_observation_earlier_than_identity_seal_is_blocked(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture["expected_identity_sealed_utc"] = "2026-10-31T14:30:00Z"
        items = self.observations()
        items[0]["captured_utc"] = "2026-10-31T14:20:00Z"
        self.assertEqual(self.run_guard(items, fixture)["reason"],
                         "OBSERVATION_BEFORE_IDENTITY_SEAL")

    def test_womens_man_city_brighton_collision_is_blocked(self):
        items = self.observations()
        items[0]["gender"] = "women"
        self.assertIn("FIXTURE_IDENTITY_CONFLICT:gender", self.run_guard(items)["reason"])

    def test_duplicate_publisher_cannot_fake_cross_check(self):
        self.assertEqual(self.run_guard([source(), source()])["reason"], "DUPLICATED_PUBLISHER")

    def test_wrong_provider_event_id_fails_even_when_score_matches(self):
        items = self.observations()
        items[0]["source_event_id"] = "another-game"
        self.assertEqual(self.run_guard(items)["reason"], "WRONG_SOURCE_EVENT_ID")

    def test_wrong_home_or_away_team_rejected(self):
        items = self.observations()
        items[1]["home_id"] = "manchester-city-women"
        self.assertEqual(self.run_guard(items)["reason"], "FIXTURE_IDENTITY_CONFLICT:home_id")

    def test_wrong_league_rejected(self):
        items = self.observations()
        items[0]["league"] = "wsl"
        self.assertEqual(self.run_guard(items)["reason"], "FIXTURE_IDENTITY_CONFLICT:league")

    def test_same_score_conflicting_status_not_settled(self):
        items = self.observations()
        items[1]["match_status"] = "SECOND_HALF"
        self.assertEqual(self.run_guard(items)["reason"], "CROSS_SOURCE_SCORE_OR_STATUS_CONFLICT")

    def test_later_provider_score_not_accepted_without_agreement(self):
        items = self.observations()
        items[1]["score_home"] = 1
        self.assertEqual(self.run_guard(items)["status"], "HOLD")

    def test_stale_capture_rejected(self):
        items = self.observations()
        items[0]["captured_utc"] = "2026-10-31T15:35:00Z"
        self.assertEqual(self.run_guard(items)["reason"], "STALE_OR_FUTURE_CAPTURE")

    def test_stale_upstream_timestamp_cannot_be_freshened_by_capture(self):
        # Two individually <=10min intervals can yield a >10min-old feed.
        items = self.observations()
        for item in items:
            item["captured_utc"] = "2026-10-31T15:51:00Z"
            item["source_updated_utc"] = "2026-10-31T15:42:00Z"
        result = self.run_guard(items, now="2026-10-31T15:59:00Z")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "STALE_OR_FUTURE_SOURCE_UPDATE")

    def test_source_timestamp_exactly_ten_minutes_old_allowed_for_research(self):
        items = self.observations()
        for item in items:
            item["source_updated_utc"] = "2026-10-31T15:49:00Z"
        result = self.run_guard(items, now="2026-10-31T15:59:00Z")
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["settlement_certified"])

    def test_future_updated_time_rejected(self):
        items = self.observations()
        items[0]["source_updated_utc"] = "2026-10-31T15:52:00Z"
        self.assertEqual(self.run_guard(items)["reason"], "STALE_OR_FUTURE_SOURCE_UPDATE")

    def test_time_shift_rejected(self):
        items = self.observations()
        items[0]["kickoff_utc"] = "2026-10-31T14:30:00Z"
        self.assertEqual(self.run_guard(items)["reason"], "SOURCE_KICKOFF_CONFLICT")

    def test_same_provider_different_fixture_url_rejected(self):
        items = self.observations()
        items[0]["source_url"] = "https://www.fotmob.com/en-GB/matches/womens-city-vs-brighton/another-event"
        self.assertEqual(self.run_guard(items)["reason"], "SOURCE_EVENT_URL_MISMATCH")

    def test_wrong_host_even_when_name_correct_rejected(self):
        items = self.observations()
        items[0]["source_url"] = "https://www.sofascore.com/football/match/"
        self.assertEqual(self.run_guard(items)["reason"], "SOURCE_EVENT_URL_MISMATCH")

    def test_fake_https_host_rejected(self):
        items = self.observations()
        items[0]["source_url"] = "https://www.fotmob.com.attacker.example/matches/"
        self.assertEqual(self.run_guard(items)["reason"], "SOURCE_EVENT_URL_MISMATCH")

    def test_early_full_time_rejected(self):
        items = self.observations()
        for item in items:
            item["match_status"] = "FINISHED"
        self.assertEqual(self.run_guard(items)["reason"], "IMPOSSIBLE_EARLY_FINAL")

    def test_actual_full_time_same_score_not_independent_authentication(self):
        items = self.observations()
        for item in items:
            item["match_status"] = "FINISHED"
            item["captured_utc"] = "2026-10-31T16:59:00Z"
            item["source_updated_utc"] = "2026-10-31T16:58:00Z"
        r = self.run_guard(items, now="2026-10-31T17:00:00Z")
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertFalse(r["settlement_certified"])

    def test_future_capture_rejected(self):
        items = self.observations()
        items[0]["captured_utc"] = "2026-10-31T15:53:00Z"
        self.assertEqual(self.run_guard(items)["reason"], "STALE_OR_FUTURE_CAPTURE")

    def test_no_prior_provider_ids_rejected(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture["provider_event_ids"] = {"fotmob": "5795502"}
        self.assertEqual(self.run_guard(fixture=fixture)["reason"], "MISSING_PRIOR_PROVIDER_IDS")

    def test_naive_clock_fails_closed(self):
        items = self.observations()
        items[0]["captured_utc"] = "2026-10-31T15:50:00"
        self.assertEqual(self.run_guard(items)["status"], "HOLD")

    def test_observations_with_bool_score_are_rejected(self):
        items = self.observations()
        items[1]["score_home"] = True
        self.assertEqual(self.run_guard(items)["reason"], "INVALID_SCORE")

    def test_prematch_with_goals_fails(self):
        items = self.observations()
        for item in items:
            item["match_status"] = "NOT_STARTED"
        self.assertEqual(self.run_guard(items)["reason"], "STALE_PREMATCH_STATUS")

    def test_empty_provider_list_fails_closed(self):
        self.assertEqual(self.run_guard([])["reason"], "NEED_AT_LEAST_TWO_OBSERVATIONS")


if __name__ == "__main__":
    unittest.main()
