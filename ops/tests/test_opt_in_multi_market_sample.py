import json
import sys
import unittest
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opt_in_multi_market_sample import collect_sample

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


class OptInMultiMarketSampleTests(unittest.TestCase):
    def test_quota_reserve_prevents_paid_odds_request(self):
        with patch("opt_in_multi_market_sample.verify", return_value={
            "quota": {"used": 100, "remaining": 145},
            "supported": {"epl": True}, "active": {"epl": True},
        }), patch("opt_in_multi_market_sample.retrieve") as retrieve:
            result = collect_sample("fake-key", "epl", now=NOW)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "QUOTA_RESERVE")
        retrieve.assert_not_called()

    def test_missing_quota_headers_fail_closed(self):
        with patch("opt_in_multi_market_sample.verify", return_value={
            "quota": {"used": 100, "remaining": 250},
            "supported": {"epl": True}, "active": {"epl": True},
        }), patch("opt_in_multi_market_sample.retrieve", return_value=(
            [], {"used": None, "remaining": None, "last": None}
        )):
            result = collect_sample("fake-key", "epl", now=NOW)
        self.assertEqual(result["reason"], "MISSING_QUOTA_HEADERS")

    def test_single_league_and_three_markets(self):
        with patch("opt_in_multi_market_sample.verify", return_value={
            "quota": {"used": 100, "remaining": 250},
            "supported": {"epl": True}, "active": {"epl": True},
        }), patch("opt_in_multi_market_sample.retrieve", return_value=(
            [], {"used": 103, "remaining": 247, "last": 3}
        )) as retrieve:
            result = collect_sample("fake-key", "epl", now=NOW)
        self.assertEqual(result["status"], "HOLD")
        kwargs = retrieve.call_args.kwargs
        self.assertEqual(kwargs["params"]["markets"], "h2h,spreads,totals")
        self.assertEqual(kwargs["params"]["regions"], "eu")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_dry_run_cli_never_queries_provider(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "dry.json"
            run = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parents[1] /
                                     "opt_in_multi_market_sample.py"),
                 "--league", "epl", "--dry-run", "--output", str(output)],
                capture_output=True, text=True, timeout=10,
                env={"PATH": "", "THE_ODDS_API_KEY": ""},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(output.read_text())
            self.assertEqual(result["api_requests_made"], 0)
            self.assertEqual(result["status"], "DRY_RUN")
            self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_missing_key_never_calls_provider(self):
        with patch("opt_in_multi_market_sample.verify") as verify:
            result = collect_sample("", "epl", now=NOW)
        self.assertEqual(result["reason"], "MISSING_KEY")
        verify.assert_not_called()

    def test_invalid_league_never_calls_provider(self):
        with patch("opt_in_multi_market_sample.verify") as verify:
            with self.assertRaises(ValueError):
                collect_sample("fake-key", "unknown", now=NOW)
        verify.assert_not_called()


class NoUtcOffset(tzinfo):
    def utcoffset(self, value):
        return None


class MultiMarketResponseClockTests(unittest.TestCase):
    """Exercise the real audit with a slow, mocked three-market response."""

    def sample(self, *, updated, kickoff=None):
        return [{
            "id": "clock-event", "sport_key": "soccer_epl",
            "home_team": "Home", "away_team": "Away",
            "commence_time": (kickoff or NOW + timedelta(hours=2)).isoformat(),
            "bookmakers": [{"key": "private-clock-book", "markets": [
                {"key": "h2h", "last_update": updated.isoformat(),
                 "outcomes": [{"name": "Home", "price": 2.2},
                              {"name": "Draw", "price": 3.1},
                              {"name": "Away", "price": 3.4}]},
                {"key": "spreads", "last_update": updated.isoformat(),
                 "outcomes": [{"name": "Home", "point": -0.25, "price": 1.91},
                              {"name": "Away", "point": 0.25, "price": 1.95}]},
                {"key": "totals", "last_update": updated.isoformat(),
                 "outcomes": [{"name": "Over", "point": 2.5, "price": 1.92},
                              {"name": "Under", "point": 2.5, "price": 1.94}]},
            ]}],
        }]

    def run_live(self, payload, *, completed=NOW + timedelta(seconds=60)):
        timeline = {"current": NOW}
        events = []

        class ResponseClock(datetime):
            @classmethod
            def now(cls, tz=None):
                events.append("clock")
                return timeline["current"].astimezone(tz)

        def catalog(*args, **kwargs):
            events.append("verify")
            timeline["current"] += timedelta(seconds=20)
            return {"quota": {"used": 100, "remaining": 250},
                    "supported": {"epl": True}, "active": {"epl": True}}

        def response(*args, **kwargs):
            events.append("retrieve")
            timeline["current"] = completed
            return payload, {"used": 103, "remaining": 247, "last": 3}

        opener = object()
        with patch("opt_in_multi_market_sample.datetime", ResponseClock), \
                patch("opt_in_multi_market_sample.verify", side_effect=catalog) as verify, \
                patch("opt_in_multi_market_sample.retrieve", side_effect=response) as retrieve:
            result = collect_sample("fake-key", "epl", opener=opener)
        verify.assert_called_once_with("fake-key", opener=opener)
        retrieve.assert_called_once_with(
            "/sports/soccer_epl/odds/", "fake-key", opener=opener,
            params={"regions": "eu", "markets": "h2h,spreads,totals",
                    "oddsFormat": "decimal", "dateFormat": "iso"})
        return result, events

    def test_quote_published_during_slow_request_uses_completed_response(self):
        payload = self.sample(updated=NOW + timedelta(seconds=30))
        original = deepcopy(payload)
        result, events = self.run_live(payload)
        self.assertEqual(events, ["verify", "retrieve", "clock"])
        self.assertEqual(result["captured_utc"], (NOW + timedelta(seconds=60)).isoformat())
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["complete_prematch_bookmaker_lines_by_market"],
                         {"h2h": 1, "spreads": 1, "totals": 1})
        self.assertEqual(payload, original)
        self.assertFalse(result["raw_prices_persisted"])
        self.assertFalse(result["bookmaker_prices_persisted"])
        self.assertFalse(result["independent_model_ev_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertNotIn("private-clock-book", json.dumps(result))
        self.assertNotIn("decimal_odds", json.dumps(result))

    def test_quote_expiring_during_request_is_rejected(self):
        result, _ = self.run_live(self.sample(updated=NOW - timedelta(seconds=90)))
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["rejections"], {"STALE_OR_FUTURE_MARKET": 3})
        self.assertEqual(result["missing_markets"], ["h2h", "spreads", "totals"])

    def test_kickoff_buffer_is_checked_at_response_completion(self):
        result, _ = self.run_live(self.sample(
            updated=NOW, kickoff=NOW + timedelta(seconds=630)))
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["rejections"], {"IN_PLAY_OR_TOO_LATE": 7})

    def test_existing_age_boundaries_use_completion_without_relaxation(self):
        completed = NOW + timedelta(seconds=60)
        for age, expected in ((120, "RESEARCH_ONLY"), (120.000001, "HOLD"),
                              (-10, "RESEARCH_ONLY"), (-10.000001, "HOLD")):
            with self.subTest(age=age):
                result, _ = self.run_live(self.sample(
                    updated=completed - timedelta(seconds=age)))
                self.assertEqual(result["status"], expected)

    def test_existing_kickoff_buffer_boundary_uses_completion(self):
        completed = NOW + timedelta(seconds=60)
        for distance, expected in ((600, "HOLD"), (600.000001, "RESEARCH_ONLY")):
            with self.subTest(distance=distance):
                result, _ = self.run_live(self.sample(
                    updated=NOW, kickoff=completed + timedelta(seconds=distance)))
                self.assertEqual(result["status"], expected)

    def test_explicit_replay_clock_stays_fixed_and_normalizes_to_utc(self):
        catalog = {"quota": {"used": 100, "remaining": 250},
                   "supported": {"epl": True}, "active": {"epl": True}}
        for cutoff in (NOW, NOW.astimezone(timezone(timedelta(hours=8)))):
            with self.subTest(cutoff=cutoff):
                with patch("opt_in_multi_market_sample.verify", return_value=catalog), \
                        patch("opt_in_multi_market_sample.retrieve", return_value=(
                            self.sample(updated=NOW - timedelta(seconds=30)),
                            {"used": 103, "remaining": 247, "last": 3})):
                    result = collect_sample("fake-key", "epl", now=cutoff)
                self.assertEqual(result["captured_utc"], NOW.isoformat())
                self.assertEqual(result["status"], "RESEARCH_ONLY")

    def test_invalid_explicit_clock_fails_before_any_provider_request(self):
        invalid = (False, 0, "2026-10-15T12:00:00Z", date(2026, 10, 15),
                   datetime(2026, 10, 15, 12), NOW.replace(tzinfo=NoUtcOffset()),
                   datetime.max.replace(tzinfo=timezone(-timedelta(hours=1))))
        for cutoff in invalid:
            with self.subTest(cutoff=cutoff):
                with patch("opt_in_multi_market_sample.verify") as verify, \
                        patch("opt_in_multi_market_sample.retrieve") as retrieve:
                    with self.assertRaises(ValueError):
                        collect_sample("fake-key", "epl", now=cutoff)
                verify.assert_not_called()
                retrieve.assert_not_called()

    def test_quota_guard_never_queries_or_stamps_a_response(self):
        with patch("opt_in_multi_market_sample.datetime") as clock, \
                patch("opt_in_multi_market_sample.verify", return_value={
                    "quota": {"used": 100, "remaining": 145},
                    "supported": {"epl": True}, "active": {"epl": True}}), \
                patch("opt_in_multi_market_sample.retrieve") as retrieve:
            result = collect_sample("fake-key", "epl")
        self.assertEqual(result["reason"], "QUOTA_RESERVE")
        retrieve.assert_not_called()
        clock.now.assert_not_called()


if __name__ == "__main__":
    unittest.main()
