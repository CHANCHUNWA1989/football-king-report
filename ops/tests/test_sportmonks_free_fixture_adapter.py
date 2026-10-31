"""Synthetic only: Sportmonks 271/501 fixture discovery and fail-closed archive."""
import copy
import json
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from secondary_sources import collect
from source_publish_guard import verify
from sportmonks_free_fixture_adapter import extract_free_fixtures, MAX_PUBLIC_ROWS


def make_fixture(day="2026-10-31", league_id=271, event_id=100,
                 reverse=False, state=1):
    kickoff = datetime.fromisoformat(day + "T12:00:00+00:00")
    home = {"id": 101, "name": "Home Eleven", "meta": {"location": "home"}}
    away = {"id": 102, "name": "Away Eleven", "meta": {"location": "away"}}
    return {
        "id": event_id,
        "league_id": league_id,
        "starting_at_timestamp": int(kickoff.timestamp()),
        "state_id": state,
        "participants": [away, home] if reverse else [home, away],
    }


class MockResponse:
    def __init__(self, body):
        self.blob = json.dumps(body).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, maximum):
        return self.blob[:maximum]


class SportmonksFreeFixturesTests(unittest.TestCase):
    def test_two_permitted_leagues_and_home_away_identity(self):
        body = {"data": [
            make_fixture(league_id=271, event_id=1, reverse=True),
            make_fixture(league_id=501, event_id=2),
            make_fixture(league_id=39, event_id=3),
        ]}
        rows, partial = extract_free_fixtures(body, expected_day="2026-10-31")
        self.assertEqual(len(rows), 2)
        self.assertFalse(partial)
        self.assertEqual(rows[0]["home"], "Home Eleven")
        self.assertEqual(rows[0]["away"], "Away Eleven")
        self.assertEqual({x["league"] for x in rows},
                         {"denmark_superliga", "scottish_premiership"})
        self.assertEqual(rows[0]["kickoff_utc"], "2026-10-31T12:00:00+00:00")

    def test_wrong_day_not_published_as_fresh(self):
        rows, _ = extract_free_fixtures(
            {"data": [make_fixture(day="2026-11-02")]},
            expected_day="2026-10-31")
        self.assertEqual(rows, [])

    def test_missing_or_invalid_participants_discarded(self):
        fixture = make_fixture()
        fixture["participants"][0]["meta"] = {}
        self.assertEqual(extract_free_fixtures(
            {"data": [fixture]}, expected_day="2026-10-31")[0], [])
        duplicate = make_fixture()
        duplicate["participants"][1]["id"] = 101
        self.assertEqual(extract_free_fixtures(
            {"data": [duplicate]}, expected_day="2026-10-31")[0], [])

    def test_no_epoch_means_no_guessed_utc(self):
        fixture = make_fixture()
        del fixture["starting_at_timestamp"]
        fixture["starting_at"] = "2026-10-31 12:00:00"
        self.assertEqual(extract_free_fixtures(
            {"data": [fixture]}, expected_day="2026-10-31")[0], [])

    def test_finished_without_score_remains_unknown(self):
        row, _ = extract_free_fixtures(
            {"data": [make_fixture(state=5)]}, expected_day="2026-10-31")
        self.assertEqual(row[0]["status"], "UNKNOWN")
        self.assertNotIn("score_ft", row[0])

    def test_pagination_reports_partial_not_complete(self):
        rows, partial = extract_free_fixtures(
            {"data": [make_fixture()], "pagination": {"current_page": 1, "has_more": True}},
            expected_day="2026-10-31")
        self.assertTrue(partial)
        self.assertEqual(len(rows), 1)

    def test_provider_error_and_page_mismatch_fail(self):
        with self.assertRaises(ValueError):
            extract_free_fixtures({"data": [], "errors": ["blocked"]},
                                  expected_day="2026-10-31")
        with self.assertRaises(ValueError):
            extract_free_fixtures({"data": [], "pagination": {"current_page": 2}},
                                  expected_day="2026-10-31")

    def test_public_sample_limit(self):
        games = [make_fixture(event_id=100+i) for i in range(MAX_PUBLIC_ROWS+2)]
        rows, partial = extract_free_fixtures(
            {"data": games}, expected_day="2026-10-31")
        self.assertEqual(len(rows), MAX_PUBLIC_ROWS)
        self.assertTrue(partial)

    def test_no_key_makes_no_sportmonks_calls(self):
        seen = []
        def requester(req, timeout):
            seen.append(req.full_url)
            return MockResponse({"events": []})
        result = collect(now=datetime.now(timezone.utc), keys={}, requester=requester)
        self.assertEqual(result["providers"][3]["status"], "NOT_CONFIGURED")
        self.assertFalse(any("sportmonks" in u for u in seen))

    def _run_with_key(self):
        now = datetime.now(timezone.utc)
        seen = []
        def requester(req, timeout):
            seen.append((req.full_url, dict(req.header_items())))
            if "sportmonks" in req.full_url:
                date = req.full_url.split("/fixtures/date/", 1)[1][:10]
                items = [
                    make_fixture(date, 271, 200+int(date[-2:])),
                    make_fixture(date, 501, 400+int(date[-2:])),
                    make_fixture(date, 39, 900+int(date[-2:])),
                ]
                return MockResponse({"data": items, "pagination": {"has_more": False}})
            return MockResponse({"events": []})
        payload = collect(now=now, keys={"SPORTMONKS_API_TOKEN": "synthetic_unique_token_never_log"},
                          requester=requester)
        return payload, seen, now

    def test_connects_two_day_free_fixtures_within_budget(self):
        payload, seen, now = self._run_with_key()
        sm = payload["providers"][3]
        self.assertEqual(sm["calls_attempted"], 2)
        self.assertEqual(sm["status"], "PARTIAL_COVERAGE")
        self.assertEqual(sm["additional_non_target_free_leagues"], 2)
        self.assertEqual(sm["free_fixture_count"], 4)
        self.assertEqual(len(sm["free_fixture_samples"]), 4)
        self.assertTrue(sm["free_fixture_data_is_only_research"])
        self.assertEqual(payload["sampled_fixtures"], [])
        self.assertIsNotNone(verify(payload, now=datetime.now(timezone.utc)))
        self.assertEqual(payload["production_recommendations"], "DISABLED")
        self.assertEqual(sum("sportmonks" in url for url, _ in seen), 2)

    def test_api_key_never_enters_url_or_snapshot(self):
        payload, seen, _ = self._run_with_key()
        self.assertNotIn("synthetic_unique_token_never_log", json.dumps(payload))
        self.assertTrue(all("api_token=" not in url for url, _ in seen))
        self.assertTrue(all("synthetic_unique_token_never_log" not in url
                            for url, _ in seen))

    def test_guard_blocks_forged_count_and_nonfree_league(self):
        payload, _, _ = self._run_with_key()
        forged = copy.deepcopy(payload)
        forged["providers"][3]["free_fixture_count"] += 1
        with self.assertRaisesRegex(ValueError, "UNSAFE_SPORTMONKS"):
            verify(forged)
        forged = copy.deepcopy(payload)
        forged["providers"][3]["free_fixture_samples"][0]["league"] = "epl"
        with self.assertRaisesRegex(ValueError, "UNSAFE_SPORTMONKS"):
            verify(forged)

    def test_guard_rejects_raw_odds_field_and_duplicate_fixture(self):
        payload, _, _ = self._run_with_key()
        forged = copy.deepcopy(payload)
        forged["providers"][3]["free_fixture_samples"][0]["decimal_price"] = 5.25
        with self.assertRaisesRegex(ValueError, "UNSAFE_SPORTMONKS"):
            verify(forged)
        forged = copy.deepcopy(payload)
        forged["providers"][3]["free_fixture_samples"][1] = copy.deepcopy(
            forged["providers"][3]["free_fixture_samples"][0])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SPORTMONKS"):
            verify(forged)

    def test_guard_rejects_missing_key_pretending_connected(self):
        payload, _, _ = self._run_with_key()
        forged = copy.deepcopy(payload)
        forged["providers"][3]["configured"] = False
        with self.assertRaisesRegex(ValueError, "UNSAFE_SPORTMONKS"):
            verify(forged)


if __name__ == "__main__":
    unittest.main()
