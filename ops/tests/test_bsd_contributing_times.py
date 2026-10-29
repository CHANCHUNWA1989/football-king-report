"""A BSD vector must retain both freshness and prediction-cutoff clocks."""
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bsd_free import collect
from bsd_guard import should_replace, validate
from bsd_overlay import build
from research_market_failover import route


NOW = datetime(2026, 10, 29, 20, tzinfo=timezone.utc)


class Response:
    def __init__(self, document):
        self.body = json.dumps(document).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body[:limit]


def source(ages, *, captured=NOW):
    """Three synthetic responses; the explicit fake client makes no requests."""
    kickoff = captured + timedelta(days=2)
    documents = [
        {"results": [{"id": 80, "name": "Bundesliga", "country": "Germany"}]},
        {"results": [{
            "id": 12345, "league_id": 80, "home_team": "Bayern Munich",
            "away_team": "Dortmund", "status": "upcoming",
            "start_time": kickoff.isoformat(),
        }]},
        {"results": [{
            "event_id": 12345, "market": "1x2", "outcome": outcome,
            "decimal_odds": price, "bookmaker_slug": "consensus",
            "updated_at": (captured - age).isoformat(),
        } for (outcome, price), age in zip(
            (("HOME", 1.7), ("DRAW", 3.9), ("AWAY", 5.7)), ages)]},
    ]

    def fake_client(request, timeout):
        index = (0 if "/leagues/" in request.full_url else
                 1 if "/events/" in request.full_url else 2)
        return Response(documents[index])

    return collect(now=captured, token="SYNTHETIC-NON-CREDENTIAL", client=fake_client)


def shadow(*, captured=NOW):
    prediction = captured + timedelta(seconds=30)
    return {
        "status": "SHADOW_ONLY", "as_of_utc": prediction.isoformat(),
        "production_recommendations": "DISABLED",
        "predictions": [{
            "event_id": "synthetic-999", "league": "bundesliga",
            "home": "Bayern Munich", "away": "Dortmund",
            "kickoff_utc": (captured + timedelta(days=2)).isoformat(),
            "prediction_utc": prediction.isoformat(),
            "p_home": 0.62, "p_draw": 0.22, "p_away": 0.16,
            "production_recommendations": "DISABLED",
        }],
    }


class BSDContributingTimesTests(unittest.TestCase):
    def assert_fallback(self, data, pairs, *, now=NOW, captured=NOW):
        overlay = build(shadow(captured=captured), data, now=now)
        routed = route({"source_state": "HOLD"}, overlay, now=now)
        self.assertEqual(overlay["time_valid_shadow_pairs"], pairs)
        self.assertEqual(overlay["status"], "RESEARCH_ONLY" if pairs else "HOLD")
        self.assertEqual(routed["status"], "BSD_FREE_RESEARCH_CONSENSUS_BACKUP" if pairs
                         else "NO_FRESH_COMPARABLE_RESEARCH_MARKET")
        self.assertEqual(routed["production_recommendations"], "DISABLED")
        self.assertFalse(routed["executable_bookmaker_quote_available"])

    def test_three_fresh_unequal_updates_preserve_both_clocks(self):
        data = source([timedelta(minutes=n) for n in (30, 20, 10)])
        row = data["events"][0]
        self.assertEqual(row["market_last_update_utc"], (NOW-timedelta(minutes=10)).isoformat())
        self.assertEqual(row.get("oldest_leg_update_utc"), (NOW-timedelta(minutes=30)).isoformat())
        self.assertEqual(validate(data, now=NOW), NOW)
        self.assertEqual(data["requests_attempted"], 3)
        self.assertNotIn("decimal_odds", json.dumps(data))
        self.assert_fallback(data, 1)

    def test_one_fresh_leg_cannot_refresh_eleven_hour_old_vector(self):
        data = source([timedelta(hours=11), timedelta(hours=11), timedelta(0)])
        self.assertEqual(data["market_count"], 1)  # The collector still admits up to 12h.
        self.assertEqual(validate(data, now=NOW), NOW)
        self.assert_fallback(data, 0)

    def test_oldest_leg_eight_hour_boundary_uses_actual_display_time(self):
        data = source([timedelta(hours=8), timedelta(minutes=20), timedelta(0)])
        self.assert_fallback(data, 1)
        self.assert_fallback(data, 0, now=NOW+timedelta(microseconds=1))

    def test_elapsed_time_does_not_refresh_a_once_valid_vector(self):
        data = source([timedelta(hours=6), timedelta(minutes=20), timedelta(0)])
        self.assert_fallback(data, 1)
        self.assert_fallback(data, 0, now=NOW+timedelta(hours=3))

    def test_newest_direction_after_frozen_prediction_stays_rejected(self):
        data = source([timedelta(minutes=30), timedelta(minutes=20), -timedelta(minutes=1)])
        self.assertEqual(data["market_count"], 1)  # Existing +5m collector tolerance.
        self.assertEqual(data["events"][0]["market_last_update_utc"],
                         (NOW+timedelta(minutes=1)).isoformat())
        self.assertEqual(validate(data, now=NOW), NOW)
        self.assert_fallback(data, 0)

    def test_direction_older_than_twelve_hours_cannot_form_vector(self):
        data = source([timedelta(hours=13), timedelta(minutes=20), timedelta(0)])
        self.assertEqual(data["market_count"], 0)
        self.assertEqual(validate(data, now=NOW), NOW)
        self.assert_fallback(data, 0)

    def test_new_event_without_oldest_provenance_is_rejected(self):
        data = source([timedelta(minutes=30)]*3)
        data["events"][0].pop("oldest_leg_update_utc", None)
        with self.assertRaises(ValueError):
            validate(data, now=NOW)
        self.assert_fallback(data, 0)

    def test_invalid_or_reversed_oldest_clock_is_rejected(self):
        for bad in (None, True, "invalid", "2026-10-29T19:00:00",
                    (NOW+timedelta(minutes=1)).isoformat(),
                    (NOW+timedelta(days=3)).isoformat()):
            with self.subTest(oldest=bad):
                data = source([timedelta(minutes=30)]*3)
                data["events"][0]["oldest_leg_update_utc"] = bad
                with self.assertRaises((ValueError, TypeError)):
                    validate(data, now=NOW)
                self.assert_fallback(data, 0)

    def test_new_data_replaces_legacy_cache_but_legacy_cannot_pair(self):
        data = source([timedelta(minutes=30)]*3)
        legacy = source([timedelta(minutes=30)]*3, captured=NOW-timedelta(minutes=1))
        legacy["events"][0].pop("oldest_leg_update_utc", None)
        with patch("bsd_guard.datetime") as clock:
            clock.now.return_value = NOW
            self.assertTrue(should_replace(data, legacy))
        self.assert_fallback(legacy, 0, captured=NOW-timedelta(minutes=1))

    def test_old_legacy_archive_can_be_replaced_without_freshness_backfill(self):
        data = source([timedelta(minutes=30)]*3)
        legacy = source([timedelta(minutes=30)]*3, captured=NOW-timedelta(days=8))
        legacy["events"][0].pop("oldest_leg_update_utc", None)
        with patch("bsd_guard.datetime") as clock:
            clock.now.return_value = NOW
            self.assertTrue(should_replace(data, legacy))
        self.assert_fallback(legacy, 0, captured=NOW-timedelta(days=8))

    def test_explicit_bad_oldest_clock_cannot_masquerade_as_legacy_archive(self):
        data = source([timedelta(minutes=30)]*3)
        old = copy.deepcopy(data)
        old["captured_utc"] = (NOW-timedelta(minutes=1)).isoformat()
        old["events"][0]["oldest_leg_update_utc"] = "invalid"
        with patch("bsd_guard.datetime") as clock:
            clock.now.return_value = NOW
            with self.assertRaises((ValueError, TypeError)):
                should_replace(data, old)

    def test_future_legacy_archive_is_not_validated_at_its_own_future_clock(self):
        data = source([timedelta(minutes=30)]*3)
        legacy = source([timedelta(minutes=30)]*3, captured=NOW+timedelta(minutes=6))
        legacy["events"][0].pop("oldest_leg_update_utc", None)
        with patch("bsd_guard.datetime") as clock:
            clock.now.return_value = NOW
            with self.assertRaisesRegex(ValueError, "BSD_STALE_OR_FUTURE_CAPTURE"):
                should_replace(data, legacy)

    def test_incoming_future_capture_keeps_existing_rejection(self):
        data = source([timedelta(minutes=30)]*3, captured=NOW+timedelta(minutes=6))
        with self.assertRaisesRegex(ValueError, "BSD_STALE_OR_FUTURE_CAPTURE"):
            validate(data, now=NOW)
        with patch("bsd_guard.datetime") as clock:
            clock.now.return_value = NOW
            with self.assertRaisesRegex(ValueError, "BSD_STALE_OR_FUTURE_CAPTURE"):
                should_replace(data, None)

    def test_existing_zero_event_status_needs_no_backfilled_clock(self):
        data = collect(now=NOW, token="")
        self.assertEqual(validate(data, now=NOW), NOW)
        self.assertEqual(data["events"], [])
        self.assert_fallback(data, 0)


if __name__ == "__main__":
    unittest.main()
