"""Free source research extensions: verified schema, quota, secure keys, licence."""
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_extensions import (
    collect, parse_statsbomb_competitions, parse_openfoot_competitions,
    parse_openfoot_matches, CATALOG)
from research_extensions_guard import validate, latest_is_newer


class FakePayload:
    def __init__(self, value):
        self.raw = json.dumps(value).encode("utf-8")
    def read(self, n):
        return self.raw[:n]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class ExtraFreeFeedsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.openfoot_matches = {
            "data":[{"id":"match_001", "competitionId":"comp_bundesliga_de",
                     "kickoffAt":(self.now+timedelta(days=1)).isoformat(),
                     "status":"scheduled","homeTeam":{"name":"Bayern"},
                     "awayTeam":{"name":"Dortmund"}}],
            "meta":{"count":1,"access":{"plan":"free"}}}
        self.statsbomb_competitions = [
            {"competition_id":9, "season_id":281, "competition_name":"1. Bundesliga",
             "season_name":"2023/2024","match_available":"2024-05-12T11:00:00"},
            {"competition_id":11, "season_id":90, "competition_name":"La Liga",
             "season_name":"2020/2021"}
        ]

    def fake(self, req, timeout):
        url=req.full_url
        if url == CATALOG:
            return FakePayload(self.statsbomb_competitions)
        if url.endswith("/v1/competitions"):
            return FakePayload({"data":[{"id":"comp_bundesliga_de"}], "meta":{}})
        if "/v1/matches?date=" in url:
            return FakePayload(self.openfoot_matches)
        raise AssertionError("UNEXPECTED_EXTERNAL_CALL")

    def test_statsbomb_historical_catalog_without_any_secret(self):
        out=collect(keys={},requester=self.fake,now=self.now)
        self.assertEqual(len(out["providers"]),2)
        self.assertEqual(out["providers"][0]["status"],"NOT_CONFIGURED")
        self.assertEqual(out["providers"][1]["status"],"HISTORICAL_CATALOG_READY")
        self.assertEqual(out["providers"][1]["catalogue_entries"],2)
        self.assertTrue(out["providers"][1]["official_attribution_required"])
        self.assertFalse(out["historical_statsbomb_results_are_live"])
        self.assertTrue(out["no_provider_raw_data_redistributed"])
        self.assertTrue(validate(out,now=self.now+timedelta(minutes=2)))

    def test_openfoot_free_with_separate_key_only_three_requests(self):
        secret="EXTENSION_SENTINEL_TEST_SUPERSECRET"
        called=[]
        def intercept(req, timeout):
            called.append((req.full_url,dict(req.header_items())))
            return self.fake(req,timeout)
        out=collect(keys={"OPENFOOT_API_KEY":secret},requester=intercept,now=self.now)
        item=out["providers"][0]
        self.assertEqual(item["status"],"FREE_STARTER_SAMPLE_ONLY")
        self.assertEqual(item["attempted_requests"],3)
        self.assertEqual(item["catalogue_entries"],1)
        self.assertEqual(item["observed_fixtures"],2)
        self.assertEqual(item["utc_kickoffs"],2)
        self.assertFalse(item["supports_verified_bookmaker_1x2"])
        self.assertEqual(len(called),4)
        self.assertTrue(all(secret not in url for url,_ in called))
        self.assertNotIn(secret,json.dumps(out))
        self.assertTrue(validate(out,now=self.now+timedelta(minutes=2)))

    def test_expired_free_api_key_stops_after_first_denial(self):
        def reject(req,timeout):
            if "openfootapi.com" in req.full_url:
                raise HTTPError(req.full_url,403,"BLOCKED",None,None)
            return self.fake(req,timeout)
        out=collect(keys={"OPENFOOT_API_KEY":"INVALID"},requester=reject,now=self.now)
        self.assertEqual(out["providers"][0]["status"],"HOLD")
        self.assertEqual(out["providers"][0]["attempted_requests"],1)
        self.assertEqual(out["providers"][0]["issues"],["FREE_PLAN_ACCESS_RESTRICTED"])

    def test_missing_key_does_not_touch_provider_or_demo(self):
        called=[]
        def record(req,timeout):
            called.append(req.full_url)
            return self.fake(req,timeout)
        out=collect(keys={},requester=record,now=self.now)
        self.assertEqual(called,[CATALOG])
        self.assertEqual(out["providers"][0]["attempted_requests"],0)

    def test_statsbomb_duplicate_competitions_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_STATSBOMB_SEASONS"):
            parse_statsbomb_competitions(self.statsbomb_competitions*2)

    def test_empty_or_invalid_openfoot_response_rejected(self):
        with self.assertRaises(ValueError):
            parse_openfoot_competitions({"data":"not-an-array"})
        with self.assertRaises(ValueError):
            parse_openfoot_matches({"error":{"code":"invalid_key"}})

    def test_no_raw_odds_or_events_in_audit(self):
        def fake(req,timeout):
            if req.full_url == CATALOG:
                return FakePayload(self.statsbomb_competitions)
            if req.full_url.endswith("/v1/competitions"):
                return FakePayload({"data":[{"id":"comp_laliga"}]})
            if "/v1/matches?date=" in req.full_url:
                return FakePayload({"data":[{"kickoffAt":self.now.isoformat(),
                    "bookmaker_prices":{"home":1.50},
                    "player_private_data":"DONT_SHARE"}]})
            raise AssertionError("BAD_URL")
        out=collect(keys={"OPENFOOT_API_KEY":"TEST"},requester=fake,now=self.now)
        assert "DONT_SHARE" not in json.dumps(out)
        assert "bookmaker_prices" not in json.dumps(out)
        self.assertTrue(validate(out,now=self.now+timedelta(minutes=2)))

    def test_source_provenance_flag_cannot_claim_live_xg(self):
        out=collect(keys={},requester=self.fake,now=self.now)
        out["new_model_variables_enabled"]=True
        with self.assertRaisesRegex(ValueError,"INVALID_RESEARCH_EXTENSION_AUTHORIZATION"):
            validate(out)

    def test_raw_fixture_field_rejected_from_public_snapshot(self):
        out=collect(keys={},requester=self.fake,now=self.now)
        out["providers"][1]["raw_odds"]=[1.7,2.8,4.2]
        with self.assertRaisesRegex(ValueError,"UNAUTHORISED_RESEARCH_EXTENSION_FIELDS"):
            validate(out)

    def test_idempotency_and_newer_snapshot(self):
        out=collect(keys={},requester=self.fake,now=self.now)
        self.assertFalse(latest_is_newer(out,out))
        later=copy.deepcopy(out)
        later["completed_utc"]=(self.now+timedelta(seconds=1)).isoformat()
        self.assertTrue(latest_is_newer(later,out))


if __name__=="__main__":
    unittest.main()
