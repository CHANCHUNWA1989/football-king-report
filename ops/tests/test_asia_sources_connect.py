"""Offline, zero-API-cost validation of optional Asia connectors."""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asia_sources_connect import CITIES, collect, validate, weather_hourly, weather_url

NOW = datetime(2026, 10, 10, 7, 40, tzinfo=timezone.utc)

class Response:
    def __init__(self, data):
        self.raw = json.dumps(data).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *unused):
        return False
    def read(self, limit):
        return self.raw[:limit]

def weather():
    start = NOW.replace(minute=0, second=0) + timedelta(hours=1)
    return {
        "timezone": "GMT",
        "hourly": {
            "time": [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
                     for i in range(70)],
            "temperature_2m": [17.5] * 70,
            "precipitation": [0.3] * 70,
            "wind_speed_10m": [12.0] * 70,
        },
    }

class AsiaConnectorTests(unittest.TestCase):
    def test_weather_six_cities_no_private_keys(self):
        seen = []
        def fake(req, timeout):
            seen.append(req)
            return Response(weather())
        report = collect(now=NOW, environ={}, requester=fake)
        self.assertTrue(validate(report))
        self.assertEqual(len(seen), 6)
        self.assertEqual(report["open_meteo"]["status"], "RESEARCH_ONLY")
        self.assertEqual(report["kleague"]["status"], "NOT_CONFIGURED")
        self.assertEqual(report["kleague"]["requests_attempted"], 0)
        self.assertTrue(all("api.open-meteo.com" in r.full_url for r in seen))
        self.assertTrue(all(r["samples"] for r in report["open_meteo"]["cities"]))
        self.assertFalse(report["model_inputs_changed"])
        self.assertFalse(report["market_odds_changed"])

    def test_kleague_key_in_header_not_url_or_public_report(self):
        seen = []
        def fake(req, timeout):
            seen.append(req)
            if "kleague" in req.full_url:
                return Response({"response": {"resultCode": "00", "list": [
                    {"MEET_YEAR": "2026", "MEET_SEQ": 1}]}})
            return Response(weather())
        report = collect(now=NOW, environ={"KLEAGUE_API_KEY": "super-secret"}, requester=fake)
        self.assertEqual(len(seen), 7)
        self.assertEqual(report["kleague"]["status"], "CATALOGUE_ACCESS_ONLY")
        self.assertEqual(report["kleague"]["league_count"], 1)
        self.assertNotIn("super-secret", json.dumps(report))
        self.assertNotIn("super-secret", seen[-1].full_url)
        self.assertEqual(seen[-1].get_header("Authkey"), "super-secret")
        self.assertTrue(validate(report))
        self.assertFalse(report["kleague"]["current_fixtures_verified"])

    def test_access_denial_is_not_success(self):
        def fake(req, timeout):
            if "kleague" in req.full_url:
                return Response({"response": {"resultCode": "06", "list": []}})
            return Response(weather())
        report = collect(now=NOW, environ={"KLEAGUE_API_KEY": "key"}, requester=fake)
        self.assertEqual(report["kleague"]["status"], "KEY_OR_PARTNER_ACCESS_DENIED")
        self.assertTrue(validate(report))

    def test_provider_denial_weather_never_fabricated(self):
        def deny(req, timeout):
            raise HTTPError(req.full_url, 403, "Forbidden", None, None)
        report = collect(now=NOW, environ={}, requester=deny)
        self.assertEqual(report["open_meteo"]["status"], "HOLD")
        self.assertTrue(all(not c["samples"] for c in report["open_meteo"]["cities"]))
        self.assertTrue(validate(report))

    def test_invalid_numeric_and_times_rejected(self):
        d = weather()
        d["hourly"]["temperature_2m"] = [float("nan")] * 70
        with self.assertRaises(ValueError):
            weather_hourly(d, NOW)
        d = weather()
        d["timezone"] = "Europe/London"
        with self.assertRaises(ValueError):
            weather_hourly(d, NOW)

    def test_production_gate_and_venue_claim_fail_closed(self):
        def fake(req, timeout):
            return Response(weather())
        doc = collect(now=NOW, environ={}, requester=fake)
        doc["production_recommendations"] = "ENABLED"
        with self.assertRaisesRegex(ValueError, "PRODUCTION"):
            validate(doc)
        doc["production_recommendations"] = "DISABLED"
        doc["open_meteo"]["cities"][0]["latitude"] = 0
        with self.assertRaisesRegex(ValueError, "UNVERIFIED_LOCATION"):
            validate(doc)

    def test_only_allowlisted_coordinates(self):
        self.assertEqual(len(CITIES), 6)
        for _, _, lat, lon in CITIES:
            url = weather_url(lat, lon)
            self.assertIn("timezone=UTC", url)
            self.assertNotIn("apikey", url.lower())

if __name__ == "__main__":
    unittest.main()
