"""Synthetic request-order regressions; never evidence of real football results."""
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import secondary_sources as sources

NOW = datetime(2026, 10, 29, 14, tzinfo=timezone.utc)


class Response:
    def __init__(self, events):
        self.body = json.dumps({"events": events}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.body[:size]


def event(identity, home, away, *, league="seriea"):
    return {"idEvent": "synthetic-" + identity,
            "idLeague": str(sources.SD_BD[league]),
            "strHomeTeam": home, "strAwayTeam": away,
            "strTimestamp": "2026-10-29T19:45:00Z", "strStatus": "NS"}


class TodayFixturePriorityTests(unittest.TestCase):
    def test_today_fixtures_survive_the_eleventh_request_rate_limit(self):
        seen = []
        first = event("first", "Fiorentina", "Atalanta")
        second = event("second", "Frosinone", "Lecce")

        def requester(request, timeout):
            seen.append(request.full_url)
            if len(seen) == 11:
                raise HTTPError(request.full_url, 429, "Rate limited", None, None)
            url = urlsplit(request.full_url)
            query = parse_qs(url.query)
            if query.get("l") == [str(sources.SD_BD["seriea"])]:
                return Response([first, second] if query.get("d") == ["2026-10-29"] else [])
            if (url.path.endswith("eventsnextleague.php")
                    and query.get("id") == [str(sources.SD_BD["seriea"])]):
                return Response([second])
            return Response([])

        report = sources.collect(now=NOW, keys={}, requester=requester)
        rows = [row for row in report["sampled_fixtures"] if row["league"] == "seriea"]
        self.assertEqual({row["provider_event_id"] for row in rows},
                         {"synthetic-first", "synthetic-second"})
        self.assertEqual(len(rows), 2)  # next-league duplicates cannot inflate coverage
        self.assertEqual(len(seen), 11)  # no retries after 429
        self.assertIn("RATE_LIMITED", report["providers"][0]["warnings"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertFalse(report["six_league_independent_results_verified"])
        self.assertFalse(report["odds_fallback_confirmed"])

    def test_every_league_gets_today_before_a_seventh_request_limit(self):
        seen = []

        def requester(request, timeout):
            seen.append(request.full_url)
            if len(seen) == 7:
                raise HTTPError(request.full_url, 429, "Rate limited", None, None)
            return Response([])

        report = sources.collect(now=NOW, keys={}, requester=requester)
        for league, url in zip(sources.LEAGUES, seen[:6]):
            parsed = urlsplit(url)
            query = parse_qs(parsed.query)
            self.assertTrue(parsed.path.endswith("eventsday.php"))
            self.assertEqual(query, {"d": ["2026-10-29"],
                                     "l": [str(sources.SD_BD[league])]})
        self.assertEqual(len(seen), 7)
        self.assertEqual(report["providers"][0]["calls_attempted"], 7)
        self.assertEqual(report["providers"][0]["status"], "HOLD")

    def test_first_request_limit_stops_without_inventing_fixtures(self):
        seen = []

        def requester(request, timeout):
            seen.append(request.full_url)
            raise HTTPError(request.full_url, 429, "Rate limited", None, None)

        report = sources.collect(now=NOW, keys={}, requester=requester)
        self.assertEqual(len(seen), 1)
        self.assertEqual(report["sampled_fixtures"], [])
        self.assertEqual(report["providers"][0]["sampled_fixture_count"], 0)
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_day_query_still_caps_three_and_rejects_wrong_league(self):
        def requester(request, timeout):
            parsed = urlsplit(request.full_url)
            query = parse_qs(parsed.query)
            if (parsed.path.endswith("eventsday.php")
                    and query == {"d": ["2026-10-29"],
                                  "l": [str(sources.SD_BD["seriea"])]}):
                return Response([event("wrong", "A", "B", league="epl")]
                                + [event(str(i), "Home " + str(i), "Away " + str(i))
                                   for i in range(4)])
            return Response([])

        report = sources.collect(now=NOW, keys={}, requester=requester)
        self.assertEqual(len(report["sampled_fixtures"]), 3)
        self.assertTrue(all(row["league"] == "seriea" and row["score_ft"] is None
                            for row in report["sampled_fixtures"]))
        self.assertEqual(report["providers"][0]["calls_attempted"], 48)
        self.assertFalse(report["original_api_payload_redistributed"])

    def test_live_request_pacing_respects_minimum_start_to_start_interval(self):
        # Avoid any network or real delay. A 2-second synthetic server
        # response should require just 4.5 more seconds, not a full sleep.
        clock = [0.0]
        starts, sleeps = [], []

        def monotonic():
            return clock[0]

        def sleep(seconds):
            self.assertGreaterEqual(seconds, 0)
            sleeps.append(seconds)
            clock[0] += seconds

        def fake_fetch(*args, **kwargs):
            starts.append(clock[0])
            clock[0] += 2.0
            return {"events": []}, "OK" if len(starts) < 4 else "RATE_LIMITED"

        with patch.object(sources, "fetch", side_effect=fake_fetch), \
                patch("time.monotonic", side_effect=monotonic), \
                patch("time.sleep", side_effect=sleep):
            report = sources.collect(now=NOW, keys={})
        self.assertEqual(starts, [0.0, 6.5, 13.0, 19.5])
        self.assertEqual(sleeps, [4.5, 4.5, 4.5])
        self.assertEqual(report["providers"][0]["calls_attempted"], 4)
        self.assertIn("RATE_LIMITED", report["providers"][0]["warnings"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_slow_response_needs_no_additional_sleep(self):
        clock = [0.0]
        starts, sleeps = [], []

        def fake_fetch(*args, **kwargs):
            starts.append(clock[0])
            clock[0] += 7.25
            return {"events": []}, "OK" if len(starts) < 3 else "RATE_LIMITED"

        with patch.object(sources, "fetch", side_effect=fake_fetch), \
                patch("time.monotonic", side_effect=lambda: clock[0]), \
                patch("time.sleep", side_effect=sleeps.append):
            report = sources.collect(now=NOW, keys={})
        self.assertEqual(starts, [0, 7.25, 14.5])
        self.assertEqual(sleeps, [])
        self.assertEqual(report["providers"][0]["calls_attempted"], 3)
        self.assertIn("RATE_LIMITED", report["providers"][0]["warnings"])

    def test_live_pacing_retains_free_budget_and_cap(self):
        # No injected requester means only the controlled clock & synthetic
        # collector fetch are used; never reach the external API in CI.
        clock = [0.0]
        sleep_durations = []

        def sleep(seconds):
            sleep_durations.append(seconds)
            clock[0] += seconds

        with patch.object(sources, "fetch", return_value=({"events": []}, "OK")), \
                patch("time.monotonic", side_effect=lambda: clock[0]), \
                patch("time.sleep", side_effect=sleep):
            report = sources.collect(now=NOW, keys={})
        self.assertEqual(report["providers"][0]["calls_attempted"], 48)
        self.assertEqual(len(sleep_durations), 47)
        self.assertTrue(all(abs(x - 6.5) < 1e-9 for x in sleep_durations))
        self.assertEqual(sources.MAX_CALLS["thesportsdb"], 48)
        self.assertEqual(report["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
