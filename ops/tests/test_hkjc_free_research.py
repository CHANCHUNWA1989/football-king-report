"""Zero-network tests for HKJC odds via third-party Tipsme Free API."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hkjc_free_research import (
    SCHEMA, collect, full_market_counts, fixtures, point, validate,
    MAX_CALLS,
)

class HKJCFreeReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,10,10,8,tzinfo=timezone.utc)
        self.kickoff = self.now + timedelta(hours=3)
        self.updated = (self.now-timedelta(minutes=2)).isoformat()
        self.match = {
            "id": 10381, "kickoffUtc":self.kickoff.isoformat(),
            "home":{"nameOriginal":"Kyoto Sanga"},
            "away":{"nameOriginal":"Machida Zelvia"},
            "competition":{"nameOriginal":"Japanese Division 1"},
            "status":"scheduled", "isHkjc":True
        }
        self.board={"data":{
            "matchResult":[{"home":"3.2","draw":"3.3","away":"2.14",
                            "recordedUtc":self.updated}],
            "handicap":[{"homeLine":"+0/0.5","awayLine":"-0/0.5",
                         "home":"2.02","away":"1.86","recordedUtc":self.updated}],
            "overUnder":[{"line":"2.5","over":"1.90","under":"1.92",
                          "recordedUtc":self.updated}],
            "cornersOverUnder":[{"line":"9.5","over":"1.85","under":"1.93",
                                 "recordedUtc":self.updated}]
        }}

    def test_missing_key_no_fetch(self):
        def fail(*args):
            self.fail("never connect third party without secret")
        r=collect(key="",now=self.now,fetcher=fail)
        self.assertTrue(validate(r))
        self.assertEqual(r["requests_attempted"],0)
        self.assertEqual(r["status"],"NOT_CONFIGURED")

    def test_six_call_ceiling_and_full_market_coverage(self):
        paths=[]
        def fake(path,key):
            self.assertEqual(key,"test-secret")
            paths.append(path)
            if "/odds/hkjc" in path:
                return self.board,22
            return {"data":[self.match]},25
        report=collect(key="test-secret",now=self.now,fetcher=fake)
        self.assertTrue(validate(report))
        self.assertEqual(report["requests_attempted"],3)
        self.assertEqual(report["hkjc_boards_checked"],1)
        for field in ("fresh_had_events","fresh_handicap_events",
                      "fresh_totals_events","fresh_corners_events"):
            self.assertEqual(report[field],1)
        self.assertEqual(report["coverage_by_league"]["japan_j1"],1)
        self.assertTrue(report["not_hkjc_account_connected"])
        self.assertFalse(report["raw_quotes_published"])
        self.assertTrue(report["requests_attempted"]<=MAX_CALLS)

    def test_scoped_to_offered_hkjc_matches(self):
        self.assertEqual(len(fixtures({"data":[self.match]},now=self.now)),1)
        other=copy.deepcopy(self.match);other["isHkjc"]=False
        self.assertEqual(len(fixtures({"data":[other]},now=self.now)),0)
        other=copy.deepcopy(self.match);other["status"]="finished"
        self.assertEqual(len(fixtures({"data":[other]},now=self.now)),0)

    def test_quarter_split_handicap_is_complementary(self):
        self.assertEqual(point("-0/0.5"),-.25)
        self.assertEqual(point("+0/0.5"),.25)
        self.assertEqual(point("-0.5/-1"),-.75)
        self.assertIsNone(point("-0.3"))
        self.assertEqual(full_market_counts(self.board,self.now,self.kickoff),
                         {"had":True,"handicap":True,"goals":True,"corners":True})

    def test_bad_handicap_no_market(self):
        board=copy.deepcopy(self.board)
        board["data"]["handicap"][0]["awayLine"]="+0/0.5"
        self.assertFalse(full_market_counts(board,self.now,self.kickoff)["handicap"])

    def test_stale_and_future_odds_not_usable(self):
        board=copy.deepcopy(self.board)
        for rows in board["data"].values():
            rows[0]["recordedUtc"]=(self.now-timedelta(hours=3)).isoformat()
        self.assertFalse(any(full_market_counts(board,self.now,self.kickoff).values()))
        board["data"]["matchResult"][0]["recordedUtc"]=(self.now+timedelta(minutes=5)).isoformat()
        self.assertFalse(full_market_counts(board,self.now,self.kickoff)["had"])

    def test_quota_reserve_prevents_extra_market_calls(self):
        paths=[]
        def fake(path,key):
            paths.append(path)
            return {"data":[self.match]},3
        r=collect(key="test",now=self.now,fetcher=fake)
        self.assertEqual(r["requests_attempted"],2)
        self.assertEqual(r["hkjc_boards_checked"],0)
        self.assertEqual(len(paths),2)

    def test_auth_denial_holds(self):
        def fake(path,key):
            raise ValueError("FREE_SCOPE_DENIED_OR_AUTH_REJECTED")
        r=collect(key="test",now=self.now,fetcher=fake)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["requests_attempted"],1)
        self.assertTrue(validate(r))

    def test_no_raw_or_account_or_bet_authorization(self):
        r=collect(key="",now=self.now)
        for name,value in (
            ("raw_quotes_published",True),
            ("not_hkjc_account_connected",False),
            ("can_execute_bet",True),
            ("production_recommendations","ENABLED"),
        ):
            fake=copy.deepcopy(r);fake[name]=value
            with self.assertRaises(ValueError):
                validate(fake)

if __name__=="__main__":
    unittest.main()
