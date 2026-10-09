"""Zero-credit official free API coverage contract and Croatian team identity tests."""
import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from croatia_fixture_probe import (
    collect,candidates,team_identity,read,TSDB,SPORTSCORE,MAX_REQUESTS,
)
from live_market_research import example

NOW=datetime(2026,10,9,13,31,tzinfo=timezone.utc)


class Response:
    def __init__(self,obj):
        self.raw=json.dumps(obj).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.raw[:n]


class CroatiaFixtureProbeTests(unittest.TestCase):
    def setUp(self):
        self.urls=[]
        def fake(req,timeout):
            self.urls.append(req.full_url)
            if req.full_url.startswith(TSDB):
                return Response({"event":[{"strHomeTeam":"Sesvete"}],
                                 "events":[{
                    "strHomeTeam":"NK Sesvete",
                    "strAwayTeam":"NK Jadran Luka Ploce",
                    "strTimestamp":"2026-10-09T13:00:00Z",
                    "strLeague":"Croatian 1.NL"}]})
            if req.full_url.startswith(SPORTSCORE):
                return Response({"matches":[{
                    "home":"Sesvete","away":"Jadran LP",
                    "time":"2026-10-09T13:00:00Z",
                    "status":"live","home_score":0,"away_score":0,
                    "slug":"unknown"}]})
            raise AssertionError("DISALLOWED_URL")
        self.fake=fake

    def test_two_keyless_readonly_probes_and_source_discovery(self):
        out=collect(now=NOW,requester=self.fake)
        self.assertEqual(out["requests_attempted"],MAX_REQUESTS)
        self.assertEqual(len(self.urls),2)
        self.assertEqual(out["status"],"PARTIAL")
        self.assertEqual([x["plausible_utc_kickoffs"]
                          for x in out["provider_reports"]],[1,1])
        self.assertFalse(out["event_utc_kickoff_source_crosscheck_complete"])
        self.assertFalse(out["event_has_independently_verified_live_stats"])
        self.assertFalse(out["current_bookmaker_lines_verified"])
        self.assertFalse(out["source_score_used_to_rewrite_predictions"])
        self.assertFalse(out["live_market_model_ready"])
        self.assertIsNone(out["recommendation"])
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertNotIn("home_score",json.dumps(out))
        self.assertTrue(out["attribution_link_required_for_public_display"])

    def test_aliases_are_explicit_not_fuzzy(self):
        self.assertEqual(team_identity("NK Sesvete"),"sesvete")
        self.assertEqual(team_identity("Sesvete"),"sesvete")
        self.assertEqual(team_identity("Jadran Luka Ploče"),"jadran_lp")
        self.assertEqual(team_identity("Jadran LP"),"jadran_lp")
        self.assertIsNone(team_identity("Jadran Zagreb"))
        self.assertIsNone(team_identity("Not Sesvete"))
        self.assertIsNone(team_identity(None))

    def test_different_teams_ignored(self):
        def wrong(req,timeout):
            return Response({"events":[{"strHomeTeam":"NK Sesvete",
                                         "strAwayTeam":"Other",
                                         "strTimestamp":"2026-10-09T13:00:00Z"}]}
                            if req.full_url.startswith(TSDB)
                            else {"matches":[]})
        r=collect(now=NOW,requester=wrong)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["reason"],"NO_VERIFIED_FREE_CROATIA_FIXTURE_MATCH")

    def test_time_mismatch_not_counted_as_this_fixture(self):
        doc={"matches":[{"home":"Sesvete","away":"Jadran LP",
                         "time":"2026-10-08T13:00:00Z"}]}
        c=candidates(doc,"sportscore",("sesvete","jadran_lp"),
                     datetime(2026,10,9,13,tzinfo=timezone.utc))
        self.assertEqual(c["alias_identity_matches"],1)
        self.assertEqual(c["plausible_utc_kickoffs"],0)

    def test_naive_provider_time_not_upgraded_to_utc(self):
        doc={"events":[{"strHomeTeam":"Sesvete","strAwayTeam":"Jadran LP",
                        "strTimestamp":"2026-10-09T13:00:00"}]}
        c=candidates(doc,"thesportsdb",("sesvete","jadran_lp"),
                     datetime(2026,10,9,13,tzinfo=timezone.utc))
        self.assertEqual(c["plausible_utc_kickoffs"],0)

    def test_unexpected_case_not_relabelled_as_supported(self):
        x=example()
        x["home"]="Other Zagreb FC"
        with self.assertRaisesRegex(ValueError,"UNRECOGNIZED_CROATIA_CASE"):
            collect(x,now=NOW,requester=self.fake)

    def test_disallowed_hosts_blocked(self):
        with self.assertRaisesRegex(ValueError,"DISALLOWED_FIXTURE_SOURCE"):
            read("https://evil.example/redirect",{},opener=self.fake)

    def test_bounded_no_request_retry_on_rate_limit(self):
        seen=[]
        def bad(req,timeout):
            seen.append(req.full_url)
            raise HTTPError(req.full_url,429,"rate-limit",{},None)
        r=collect(now=NOW,requester=bad)
        self.assertEqual(r["requests_attempted"],2)
        self.assertEqual(len(seen),2)
        self.assertEqual(r["status"],"HOLD")
        self.assertTrue(all(s["reason"]=="RATE_LIMITED" for s in r["provider_reports"]))

    def test_unknown_schema_holds_and_never_mutates_model(self):
        def bad(req,timeout):return Response({"else":"undocumented"})
        r=collect(now=NOW,requester=bad)
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["source_score_used_to_rewrite_predictions"])
        self.assertFalse(r["current_bookmaker_lines_verified"])


if __name__=="__main__":
    unittest.main()
