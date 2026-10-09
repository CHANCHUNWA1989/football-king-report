"""No-key SportScore never supplies unverified market data or final score truth."""
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sportscore_probe import collect, sample_summary

NOW=datetime(2026,10,9,8,tzinfo=timezone.utc)


class Response:
    def __init__(self,payload):
        self.raw=json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n): return self.raw[:n]


class SportscoreContractTests(unittest.TestCase):
    def test_one_free_anonymous_call_with_no_betting_unlock(self):
        calls=[]
        def fake(req,timeout):
            calls.append(req.full_url)
            self.assertNotIn("apikey",req.full_url.lower())
            return Response({"matches":[{"home_team":"Arsenal","away_team":"Liverpool"},
                                        {"home_team":"Same","away_team":"Same"}]})
        result=collect(now=NOW,requester=fake)
        self.assertEqual(len(calls),1)
        self.assertEqual(result["status"],"PARTIAL")
        self.assertEqual(result["eligible_team_pair_sample"],1)
        self.assertFalse(result["final_score_independently_confirmed"])
        self.assertFalse(result["can_replace_market_odds"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertTrue(result["attribution_link_required_if_data_displayed"])

    def test_no_raw_rows_in_result(self):
        def fake(req,timeout):
            return Response({"data":[{"home_team":{"name":"Bayern"},"away_team":{"name":"Dortmund"}}]})
        result=collect(now=NOW,requester=fake)
        self.assertNotIn("Bayern",json.dumps(result))
        self.assertEqual(result["eligible_team_pair_sample"],1)

    def test_bad_schema_fails_closed(self):
        def fake(req,timeout): return Response({"matches":{"home_team":"no"}})
        result=collect(now=NOW,requester=fake)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["reason"],"SOURCE_SCHEMA_UNVERIFIED")

    def test_limit_and_invalid_pairs(self):
        with self.assertRaises(ValueError):
            sample_summary({"matches":[{}]*51})
        self.assertEqual(sample_summary({"matches":[{"home_team":"X","away_team":"X"}]})["valid_team_pair_rows"],0)

    def test_429_not_retried(self):
        seen=[]
        def fake(req,timeout):
            seen.append(1)
            raise HTTPError(req.full_url,429,"rate-limited",{},None)
        result=collect(now=NOW,requester=fake)
        self.assertEqual(len(seen),1)
        self.assertEqual(result["reason"],"RATE_LIMITED")
        self.assertEqual(result["status"],"HOLD")


    def test_documented_home_away_time_and_finished_score_schema(self):
        records={"matches":[
            {"home":"Arsenal","away":"Chelsea","time":"2026-10-08T14:00:00Z",
             "status":"finished","home_score":2,"away_score":1},
            {"home":"Liverpool","away":"Everton","time":"2026-10-11T14:00:00Z",
             "status":"upcoming","home_score":None,"away_score":None},
            {"home":"Liverpool","away":"Everton","time":"bad-time",
             "status":"finished","home_score":0,"away_score":0}
        ]}
        got=sample_summary(records)
        self.assertEqual(got["raw_fixture_rows"],3)
        self.assertEqual(got["valid_team_pair_rows"],3)
        self.assertEqual(got["source_timed_rows"],2)
        self.assertEqual(got["source_finished_score_rows"],1)
        def fake(req,timeout): return Response(records)
        result=collect(now=NOW,requester=fake)
        self.assertEqual(result["source_finished_score_rows"],1)
        self.assertFalse(result["final_score_independently_confirmed"])
        self.assertFalse(result["provider_kickoff_time_verified"])

if __name__=="__main__":
    unittest.main()
