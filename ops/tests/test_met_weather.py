"""MET Norway: source attribution, time-of-issue validity, no odds/picks."""
import copy
import json
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from met_weather import collect,extract_city,LICENSE,CITY_POINTS,USER_AGENT
from met_weather_guard import validate,replace
from met_weather_overlay import build

NOW=datetime.now(timezone.utc)
HOUR=NOW.replace(minute=0,second=0,microsecond=0)
START=HOUR+timedelta(hours=3-HOUR.hour%3)


def fixture_weather():
    return {
        "properties":{
            "meta":{"updated_at":(NOW-timedelta(minutes=8)).isoformat()},
            "timeseries":[{
                "time":(START+timedelta(hours=3*i)).isoformat(),
                "data":{
                    "instant":{"details":{"air_temperature":15.2,
                                          "wind_speed":5.4}},
                    "next_1_hours":{"details":{"precipitation_amount":0.4}}
                }
            } for i in range(10)]
        }
    }


class Response:
    def __init__(self,payload):
        self.raw=json.dumps(payload).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.raw[:n]


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.requests=[]
        def fake(req,timeout):
            self.requests.append(req)
            return Response(fixture_weather())
        self.fake=fake

    def test_six_city_free_forecast_requests_and_no_bookmaker(self):
        d=collect(now=NOW,client=self.fake)
        self.assertEqual(d["status"],"RESEARCH_ONLY")
        self.assertEqual(d["request_count"],6)
        self.assertEqual(len(d["cities"]),6)
        self.assertEqual(validate(d,now=NOW),NOW)
        self.assertTrue(all("api.met.no" in r.full_url for r in self.requests))
        self.assertIn("github.com",USER_AGENT)
        self.assertIn("creativecommons",d["license_url"])
        self.assertTrue(d["licence_attribution_required"])
        self.assertFalse(d["source_data_used_in_model"])
        self.assertFalse(d["verified_betting_advantage"])
        self.assertFalse(d["current_executable_bookmaker_odds"])
        self.assertEqual(d["production_recommendations"],"DISABLED")
        self.assertNotIn("bet365",json.dumps(d))
        self.assertTrue(all(c["hourly_samples"] for c in d["cities"]))

    def test_forecast_schema_and_unit_ranges(self):
        model,points=extract_city(fixture_weather(),NOW)
        self.assertTrue(model)
        self.assertTrue(points)
        self.assertEqual(points[0]["temperature_c"],15.2)
        self.assertEqual(points[0]["wind_speed_m_s"],5.4)
        self.assertEqual(points[0]["precipitation_next_1h_mm"],0.4)

    def test_future_issued_forecast_rejected(self):
        d=fixture_weather()
        d["properties"]["meta"]["updated_at"]=(NOW+timedelta(hours=3)).isoformat()
        with self.assertRaisesRegex(ValueError,"MET_FORECAST_ISSUE_TIME_BAD"):
            extract_city(d,NOW)

    def test_missing_temperature_not_made_up(self):
        d=fixture_weather()
        for t in d["properties"]["timeseries"]:
            t["data"]["instant"]["details"].pop("air_temperature")
        with self.assertRaisesRegex(ValueError,"MET_NO_FUTURE_HOURLY"):
            extract_city(d,NOW)

    def test_bad_request_gets_hold_not_synthetic_forecast(self):
        def deny(req,timeout):
            raise HTTPError(req.full_url,403,"Forbidden",None,None)
        d=collect(now=NOW,client=deny)
        self.assertEqual(d["status"],"HOLD")
        self.assertEqual(len(d["cities"]),6)
        self.assertTrue(all(c["status"]=="ACCESS_DENIED" for c in d["cities"]))
        self.assertTrue(all(c["hourly_samples"]==[] for c in d["cities"]))
        self.assertIsNotNone(validate(d,now=NOW))

    def test_cannot_claim_verified_betting_advantage(self):
        d=collect(now=NOW,client=self.fake)
        d["verified_betting_advantage"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_WEATHER_PROVENANCE"):
            validate(d,now=NOW)

    def test_unknown_venue_cannot_be_inferred_as_exact_stadium(self):
        d=collect(now=NOW,client=self.fake)
        d["location_accuracy"]="STADIUM_VENUE_CONFIRMED"
        with self.assertRaisesRegex(ValueError,"UNSAFE_WEATHER_PROVENANCE"):
            validate(d,now=NOW)

    def test_unexpected_thermometer_values_rejected(self):
        d=collect(now=NOW,client=self.fake)
        d["cities"][0]["hourly_samples"][0]["temperature_c"]=175
        with self.assertRaisesRegex(ValueError,"WEATHER_VALUE_RANGE_INVALID"):
            validate(d,now=NOW)

    def test_tampered_city_geo_rejected(self):
        d=collect(now=NOW,client=self.fake)
        d["cities"][0]["longitude"]=0
        with self.assertRaisesRegex(ValueError,"WEATHER_CITY_IDENTITY_INVALID"):
            validate(d,now=NOW)

    def test_history_never_downgraded_or_duplicated(self):
        d=collect(now=NOW,client=self.fake)
        self.assertFalse(replace(d,d))
        older=copy.deepcopy(d)
        older["captured_utc"]=(NOW-timedelta(minutes=20)).isoformat()
        for city in older["cities"]:
            city["model_updated_utc"]=(NOW-timedelta(minutes=28)).isoformat()
        self.assertFalse(replace(older,d))
        newer=copy.deepcopy(d)
        newer["captured_utc"]=(NOW+timedelta(minutes=1)).isoformat()
        self.assertTrue(replace(newer,d))

    def test_weather_never_calibrates_frozen_shadow_probabilities(self):
        d=collect(now=NOW,client=self.fake)
        ko=START+timedelta(hours=3)
        shadow={"status":"SHADOW_ONLY",
                "production_recommendations":"DISABLED",
                "predictions":[{
                    "league":"bundesliga","home":"Bayern Munich",
                    "away":"Borussia Dortmund","kickoff_utc":ko.isoformat(),
                    "prediction_utc":NOW.isoformat(),
                    "p_home":.65,"p_draw":.2,"p_away":.15}]}
        result=build(shadow,d,now=NOW)
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertEqual(len(result["forecasts"]),1)
        row=result["forecasts"][0]
        self.assertEqual(row["city"],"munich")
        self.assertFalse(row["used_in_model"])
        self.assertFalse(result["market_odds_source"])
        self.assertFalse(result["match_venue_confirmed"])
        self.assertFalse(result["weather_impact_on_win_probability_validated"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertNotIn("p_home",row)
        self.assertNotIn("p_home",json.dumps(result))

    def test_no_unknown_team_geocoding_or_venue_guess(self):
        d=collect(now=NOW,client=self.fake)
        shadow={"status":"SHADOW_ONLY","production_recommendations":"DISABLED",
                "predictions":[{"league":"bundesliga","home":"Unknown City FC",
                                "away":"Other Club","prediction_utc":NOW.isoformat(),
                                "kickoff_utc":(START+timedelta(hours=3)).isoformat()}]}
        r=build(shadow,d,now=NOW)
        self.assertEqual(r["forecasts"],[])

    def test_stale_report_holds(self):
        d=collect(now=NOW,client=self.fake)
        r=build({"status":"SHADOW_ONLY","production_recommendations":"DISABLED",
                 "predictions":[]},d,now=NOW+timedelta(hours=40))
        self.assertEqual(r["status"],"HOLD")


if __name__=="__main__":
    unittest.main()
