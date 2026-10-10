"""No commercial quotes or unsupported API entitlements may reach Pages."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from japan_free_market import collect
from japan_free_market_guard import check, latest_can_replace


class J1FreeGuardTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,10,12,tzinfo=timezone.utc)
        self.safe=collect({},now=self.now,requester=self.no_network)

    @staticmethod
    def no_network(*args,**kwargs):
        raise AssertionError("NO_NETWORK_REQUEST_EXPECTED")

    def test_missing_keys_status_is_safe_to_publish_but_not_connected(self):
        stamp=check(self.safe,now=self.now)
        self.assertEqual(stamp,self.now)
        self.assertEqual(self.safe["status"],"HOLD")
        self.assertFalse(self.safe["raw_bookmaker_prices_or_names_redistributed"])

    def test_raw_odds_and_bookmaker_id_not_allowed(self):
        for key,value in (("bookmakers",[]),("price_decimal",2.01),
                          ("api_key","SECRET"),("provider_original_payload",{})):
            with self.subTest(key=key):
                broken=copy.deepcopy(self.safe)
                broken[key]=value
                with self.assertRaises(ValueError):
                    check(broken,now=self.now)
        broken=copy.deepcopy(self.safe)
        broken["j1_free_prematch_sources"][0]["bookmaker"]="secret"
        with self.assertRaises(ValueError):
            check(broken,now=self.now)

    def test_no_false_qualified_provider_after_missing_key(self):
        d=copy.deepcopy(self.safe)
        first=d["j1_free_prematch_sources"][0]
        first["status"]="RESEARCH_ONLY"
        first["fresh_3way_event_count"]=10
        d["status"]="RESEARCH_ONLY"
        with self.assertRaises(ValueError):
            check(d,now=self.now)

    def test_market_cannot_enable_betting_by_mutating_safe_flags(self):
        for field,value in (
            ("production_recommendations","ENABLED"),
            ("bet_recommendation_count",1),
            ("realtime_inplay_quotes_confirmed",True),
            ("j1_model_remains_uncalibrated",False),
            ("free_tier_closing_lines_available",True),
            ("estimated_roi",0.20),
        ):
            with self.subTest(field=field):
                d=copy.deepcopy(self.safe)
                d[field]=value
                with self.assertRaises(ValueError):
                    check(d,now=self.now)

    def test_stale_or_future_capture_fails(self):
        for hour in (-49, +1):
            d=copy.deepcopy(self.safe)
            d["collected_utc"]=(self.now+timedelta(hours=hour)).isoformat()
            with self.assertRaises(ValueError):
                check(d,now=self.now)

    def test_out_of_order_update_is_not_written(self):
        older=copy.deepcopy(self.safe)
        older["collected_utc"]=(self.now-timedelta(hours=1)).isoformat()
        self.assertFalse(latest_can_replace(self.safe,older,now=self.now))
        self.assertTrue(latest_can_replace(older,self.safe,now=self.now))
        self.assertFalse(latest_can_replace(self.safe,self.safe,now=self.now))

    def test_positive_safely_aggregated_provider(self):
        d=copy.deepcopy(self.safe)
        d["status"]="RESEARCH_ONLY"
        x=d["j1_free_prematch_sources"][0]
        x.update(configured=True,status="RESEARCH_ONLY",
                 reason="FRESH_PREMATCH_RESEARCH_METADATA_ONLY",
                 requests_attempted=1,fresh_3way_event_count=2)
        self.assertEqual(check(d,now=self.now),self.now)
        self.assertFalse(d["j1_fixtures_not_independently_verified"] is False)


if __name__=="__main__":
    unittest.main()
