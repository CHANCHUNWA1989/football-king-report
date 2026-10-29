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

    def test_live_request_pacing_and_budget_are_unchanged(self):
        with patch.object(sources, "fetch", return_value=({"events": []}, "OK")), \
                patch("time.sleep") as sleep:
            report = sources.collect(now=NOW, keys={})
        self.assertEqual(report["providers"][0]["calls_attempted"], 48)
        self.assertEqual(sleep.call_count, 47)
        self.assertTrue(all(call.args == (2.35,) for call in sleep.call_args_list))


if __name__ == "__main__":
    unittest.main()
