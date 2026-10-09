"""Synthetic contracts: no real quota, no network, no secret leakage or bets."""
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from additional_free_apis import (
    ARCHIVE, METEOSTAT, OPEN_METEO, SCOREBAT, WIKIDATA,
    collect, forecast_summary, historical_summary, meteostat_summary,
    read_json, scorebat_summary, wikidata_summary, MAX_CALLS, CITY_POINTS,
)

NOW = datetime(2026, 10, 9, 8, tzinfo=timezone.utc)


class Response:
    def __init__(self, payload):
        self.data = json.dumps(payload).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, limit):
        return self.data[:limit]


def forecast():
    out = []
    for _, _, lat, lon, _ in CITY_POINTS:
        out.append({"latitude": lat, "longitude": lon, "utc_offset_seconds": 0,
                    "hourly": {
                        "time": [(NOW + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
                                 for i in range(12)],
                        "temperature_2m": [14.4] * 12,
                        "wind_speed_10m": [4.1] * 12,
                        "precipitation": [0.2] * 12}})
    return out


def archive():
    t = NOW - timedelta(days=12)
    return {"utc_offset_seconds": 0, "hourly": {
        "time": [(t + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
                 for i in range(24)],
        "temperature_2m": [10.0]*24,
        "wind_speed_10m": [3.1]*24,
        "precipitation": [0.3]*24}}


def meteostat():
    return {"data": [{"date": (NOW - timedelta(days=12)).date().isoformat(),
                      "tavg": 13.2, "prcp": 1.1},
                     {"date": (NOW - timedelta(days=11)).date().isoformat(),
                      "tavg": 11.2, "prcp": None}]}


def wikidata():
    return {"results": {"bindings": [
        {"venue": {"value": "http://www.wikidata.org/entity/Q123"},
         "coord": {"value": "Point(11.576 48.137)"}}
    ]}}


def scorebat():
    return {"response": [{"date": (NOW - timedelta(days=1)).isoformat(),
                          "homeTeam": {"name": "Everton"},
                          "awayTeam": {"name": "Arsenal"},
                          "videos": [{"title": "Highlights", "embed": "<iframe>"}]}]}


class AdditionalFreeAPITests(unittest.TestCase):
    def setUp(self):
        self.urls = []
        self.requests = []
        def requester(req, timeout):
            self.urls.append(req.full_url)
            self.requests.append(req)
            if req.full_url.startswith(OPEN_METEO):
                return Response(forecast())
            if req.full_url.startswith(ARCHIVE):
                return Response(archive())
            if req.full_url.startswith(METEOSTAT):
                return Response(meteostat())
            if req.full_url.startswith(WIKIDATA):
                return Response(wikidata())
            if req.full_url.startswith(SCOREBAT):
                return Response(scorebat())
            raise AssertionError("UNEXPECTED_ENDPOINT")
        self.fake = requester

    def test_forecast_one_batch_request_for_six_cities(self):
        doc = collect(now=NOW, keys={}, requester=self.fake)
        self.assertEqual(doc["calls_attempted"],1)
        self.assertEqual(len(self.urls),1)
        self.assertEqual(doc["providers"][0]["matched_or_valid_rows"],6)
        self.assertEqual(doc["providers"][0]["hourly_observations"],72)
        self.assertEqual(doc["production_recommendations"],"DISABLED")
        self.assertFalse(doc["model_training_changed"])
        self.assertFalse(doc["bookmaker_quotes_saved"])

    def test_weekly_all_five_sources_with_two_keys(self):
        keys={"METEOSTAT_RAPIDAPI_KEY":"private-weather-key",
              "SCOREBAT_FREE_TOKEN":"secret-video-token"}
        doc = collect(now=NOW, keys=keys, requester=self.fake, background=True)
        self.assertEqual(doc["calls_attempted"],5)
        self.assertEqual(len(self.urls),5)
        self.assertEqual(doc["valid_provider_count"],5)
        self.assertTrue(all(r["status"] in ("RESEARCH_ONLY","PARTIAL") for r in doc["providers"]))
        self.assertNotIn("private-weather-key",json.dumps(doc))
        self.assertNotIn("secret-video-token",json.dumps(doc))
        self.assertFalse(doc["private_credentials_published"])
        self.assertFalse(doc["raw_payload_published"])
        self.assertFalse(doc["betting_enabled"])
        self.assertEqual(self.requests[-2].get_header("X-rapidapi-key"),"private-weather-key")
        self.assertIn("token=secret-video-token",self.urls[-1])
        self.assertEqual(doc["production_recommendations"],"DISABLED")

    def test_no_keys_uses_only_three_no_key_services(self):
        doc = collect(now=NOW, keys={}, requester=self.fake, background=True)
        self.assertEqual(doc["calls_attempted"],3)
        self.assertEqual(doc["providers"][3]["status"],"PARTIAL")
        self.assertEqual(doc["providers"][2]["status"],"NOT_CONFIGURED")
        self.assertEqual(doc["providers"][4]["status"],"NOT_CONFIGURED")
        self.assertFalse(any("rapidapi.com" in url or "scorebat.com" in url
                             for url in self.urls))

    def test_forecast_wrong_city_coordinates_never_accepted(self):
        bad = forecast()
        bad[0]["latitude"] = 0
        self.assertEqual(forecast_summary(bad, NOW)[0],5)

    def test_forecast_future_weather_has_no_valid_rows(self):
        bad=forecast()
        for item in bad:
            item["hourly"]["time"] = [(NOW + timedelta(days=10,hours=i)).strftime(
                "%Y-%m-%dT%H:%M") for i in range(12)]
        self.assertEqual(forecast_summary(bad, NOW),(0,0))

    def test_forecast_requires_zero_utc_offset(self):
        bad=forecast()
        for item in bad:
            item["utc_offset_seconds"]=3600
        self.assertEqual(forecast_summary(bad, NOW),(0,0))

    def test_archive_reanalysis_does_not_create_prematch_data(self):
        n=historical_summary(archive(), NOW-timedelta(days=12),NOW-timedelta(days=10))
        self.assertEqual(n,24)
        wrong=archive()
        wrong["utc_offset_seconds"]=3600
        with self.assertRaises(ValueError):
            historical_summary(wrong,NOW-timedelta(days=12),NOW-timedelta(days=10))

    def test_meteostat_only_historical_observed_days(self):
        self.assertEqual(meteostat_summary(meteostat(),NOW-timedelta(days=12),
                                            NOW-timedelta(days=10)),2)
        d=meteostat()
        d["data"][0]["date"]=(NOW + timedelta(days=1)).date().isoformat()
        self.assertEqual(meteostat_summary(d,NOW-timedelta(days=12),
                                           NOW-timedelta(days=10)),1)

    def test_wikidata_bounded_results_not_auto_stadium(self):
        self.assertEqual(wikidata_summary(wikidata()),1)
        bad=wikidata()
        bad["results"]["bindings"] *= 21
        with self.assertRaises(ValueError):
            wikidata_summary(bad)

    def test_scorebat_highlights_are_not_final_scores(self):
        self.assertEqual(scorebat_summary(scorebat()),1)
        self.assertEqual(scorebat_summary({"response":[{"videos":[],"homeTeam":{}}]}),0)

    def test_upstream_429_never_retries(self):
        seen=[]
        def bad(req,timeout):
            seen.append(req.full_url)
            raise HTTPError(req.full_url,429,"quota",{},None)
        doc=collect(now=NOW,keys={},requester=bad)
        self.assertEqual(doc["calls_attempted"],1)
        self.assertEqual(doc["status"],"HOLD")
        self.assertEqual(doc["providers"][0]["reason"],"RATE_LIMITED")
        self.assertEqual(len(seen),1)

    def test_no_arbitrary_provider_url(self):
        with self.assertRaises(ValueError):
            read_json("https://evil.example/collect?secret=true",requester=self.fake)

    def test_unknown_historical_source_never_enters_model(self):
        def bad(req,timeout):
            if req.full_url.startswith(OPEN_METEO):
                return Response(forecast())
            return Response({"unknown":"schema"})
        doc=collect(now=NOW,keys={},background=True,requester=bad)
        self.assertEqual(doc["providers"][1]["status"],"HOLD")
        self.assertEqual(doc["providers"][3]["status"],"HOLD")
        self.assertFalse(doc["model_training_changed"])
        self.assertLessEqual(doc["calls_attempted"],MAX_CALLS)


if __name__=="__main__":
    unittest.main()
