"""No-network regression tests for safe additional archived FT observations."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from free_result_recovery import candidates, read_candidates
from forward_validation import extend
from forward_cohort_backlog import audit

LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
PROVIDERS = ("thesportsdb", "api_football", "football_data_org", "sportmonks")


class CachedFreeFinalTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 11, 19, tzinfo=timezone.utc)
        self.kick = self.now - timedelta(hours=4)
        self.started = self.now - timedelta(minutes=6)
        self.captured = self.now - timedelta(minutes=5)
        self.original = {
            "league": "epl", "home": "Everton", "away": "Arsenal",
            "prediction_utc": (self.kick-timedelta(days=1)).isoformat(),
            "market_snapshot_utc": (self.kick-timedelta(days=1,minutes=10)).isoformat(),
            "kickoff_utc": self.kick.isoformat(),
            "model": [.30,.30,.40], "market": [.20,.30,.50],
            "production_recommendations": "DISABLED",
        }
        self.key=("epl","everton","arsenal",self.kick.isoformat())
        self.report={"checked_utc":self.now.isoformat(),
                     "production_recommendations":"DISABLED",
                     "fixtures":{"matches":[]}}
        self.ledger={"schema":"football-king-forward-research-1",
                     "checked_utc":self.now.isoformat(),"samples":[],"n":0,
                     "results_independently_verified":False,
                     "profitability_verified":False,
                     "production_recommendations":"DISABLED"}
        self.score={
            "provider":"thesportsdb","league":"epl","home":"Everton",
            "away":"Arsenal","provider_event_id":"ft-123",
            "kickoff_utc":self.kick.isoformat(),
            "status":"FINISHED","score_ft":[1,2],
        }
        providers=[]
        for provider in PROVIDERS:
            counts={league:0 for league in LEAGUES}
            if provider=="thesportsdb":
                counts["epl"]=1
            providers.append({
                "provider":provider,
                "status":"PARTIAL_COVERAGE" if provider=="thesportsdb" else "NOT_CONFIGURED",
                "configured":provider=="thesportsdb",
                "calls_attempted":1 if provider=="thesportsdb" else 0,
                "counts_by_league":counts,
                "sampled_fixture_count":sum(counts.values()),
                "league_result_verification_complete":False,
                "can_replace_1x2_market":False,
                "original_bookmaker_odds_redistributed":False,
                "production_recommendations":"DISABLED",
                **({"recent_final_score_observations":1} if provider=="thesportsdb" else {}),
            })
        self.audit={
            "schema":"football-king-extra-source-audit-v1",
            "started_utc":self.started.isoformat(),
            "collected_utc":self.captured.isoformat(),
            "source_tier":"RESEARCH_ONLY","status":"RESEARCH_ONLY",
            "providers":providers,"sampled_fixtures":[self.score],
            "coverage_is_complete":False,
            "six_league_independent_results_verified":False,
            "odds_fallback_confirmed":False,
            "original_api_payload_redistributed":False,
            "production_recommendations":"DISABLED",
        }

    def test_zero_additional_queries_can_settle_only_presealed_case(self):
        # Original scored feed has no league result; archived public free feed
        # already holds exact FT. No future model can be retrofitted.
        self.assertEqual(
            extend({},[(self.key,self.original)],self.report)["n"],0)
        free,diag=candidates(self.audit,self.now)
        self.assertEqual(diag["accepted_free_score_candidates"],1)
        self.assertFalse(diag["independently_verified"])
        result=extend({},[(self.key,self.original)],self.report,free_result_rows=free)
        self.assertEqual(result["n"],1)
        self.assertEqual(result["samples"][0]["y"],2)
        self.assertFalse(result["results_independently_verified"])
        self.assertFalse(result["samples"][0]["fixture_result_source_independently_verified"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
        backlog=audit([(self.key,self.original)],result,self.report,free_result_rows=free)
        self.assertEqual(backlog["by_league"][0]["settled_ledger_cases"],1)
        self.assertEqual(backlog["unmatched_finished_result_backlog"],0)

    def test_identical_two_source_ft_scores_not_false_ambiguity(self):
        original_source={
            "schema":"football-king-single-source-finished-results-1",
            "captured_utc":self.now.isoformat(),
            "records":[{
                "league":"epl","home":"Everton","away":"Arsenal",
                "date":self.kick.date().isoformat(),
                "kickoff_utc":self.kick.isoformat(),
                "status":"FINISHED","score_ft":[1,2],
            }],
            "independently_verified_all_leagues":False,
            "production_recommendations":"DISABLED",
        }
        free,_=candidates(self.audit,self.now)
        result=extend({},[(self.key,self.original)],self.report,
                      original_source,free)
        self.assertEqual(result["n"],1)
        self.assertFalse(result["results_independently_verified"])
        # Multiple observations of the *same* FT are not two settled samples.
        self.assertEqual(extend(result,[(self.key,self.original)],
                                self.report,original_source,free)["newly_settled"],0)

    def test_conflicting_exact_scores_are_quarantined_even_same_outcome(self):
        self.report["fixtures"]["matches"]=[{
            "league":"epl","home":"Everton","away":"Arsenal",
            "kickoff_utc":self.kick.isoformat(),"status":"FINISHED",
            "score_ft":[0,3],
        }]
        free,_=candidates(self.audit,self.now)
        result=extend({},[(self.key,self.original)],self.report,
                      free_result_rows=free)
        self.assertEqual(result["n"],0)
        backlog=audit([(self.key,self.original)],self.ledger,
                      self.report,free_result_rows=free)
        self.assertEqual(backlog["ambiguous_finished_result_backlog"],1)
        self.assertEqual(backlog["score_observed_pending_settlement"],0)

    def test_free_only_nonfinal_or_future_final_cannot_settle(self):
        for status,score,kickoff in (
            ("SCHEDULED",None,self.kick),
            ("FINISHED",[1,2],self.now+timedelta(hours=3)),
            ("FINISHED",[1,2],self.now-timedelta(minutes=80)),
        ):
            with self.subTest(status=status,kickoff=kickoff):
                doc=copy.deepcopy(self.audit)
                doc["sampled_fixtures"][0]["status"]=status
                doc["sampled_fixtures"][0]["score_ft"]=score
                doc["sampled_fixtures"][0]["kickoff_utc"]=kickoff.isoformat()
                doc["providers"][0]["recent_final_score_observations"] = int(status=="FINISHED")
                free,diag=candidates(doc,self.now)
                self.assertEqual(free,[])
                self.assertEqual(diag["accepted_free_score_candidates"],0)
                self.assertEqual(extend({},[(self.key,self.original)],
                                        self.report,free_result_rows=free)["n"],0)

    def test_stale_snapshot_rejected_without_stopping_original_gateway(self):
        doc=copy.deepcopy(self.audit)
        doc["collected_utc"]=(self.now-timedelta(hours=50)).isoformat()
        doc["started_utc"]=(self.now-timedelta(hours=50,minutes=1)).isoformat()
        free,diag=candidates(doc,self.now)
        self.assertEqual(free,[])
        self.assertEqual(diag["reason"],"FREE_SOURCE_TOO_OLD_OR_FUTURE")
        self.report["fixtures"]["matches"]=[{
            "league":"epl","home":"Everton","away":"Arsenal",
            "kickoff_utc":self.kick.isoformat(),"status":"FINISHED",
            "score_ft":[1,2],
        }]
        settled=extend({},[(self.key,self.original)],self.report,
                       free_result_rows=free)
        self.assertEqual(settled["n"],1)

    def test_false_independent_verification_and_proprietary_field_rejected(self):
        for tweak in ("fake_verified","fake_quote","fake_provider_count","fake_status"):
            with self.subTest(tweak=tweak):
                doc=copy.deepcopy(self.audit)
                if tweak=="fake_verified":
                    doc["six_league_independent_results_verified"]=True
                elif tweak=="fake_quote":
                    doc["sampled_fixtures"][0]["raw_odds"]=2.15
                elif tweak=="fake_provider_count":
                    doc["providers"][0]["counts_by_league"]["epl"]=99
                else:
                    doc["sampled_fixtures"][0]["status"]="LIVE"
                self.assertEqual(candidates(doc,self.now)[0],[])
                self.assertEqual(candidates(doc,self.now)[1]["status"],"HOLD")

    def test_mismatched_league_team_and_utc_are_never_promoted(self):
        free,_=candidates(self.audit,self.now)
        self.assertEqual(extend({},[(self.key,{**self.original,"league":"laliga"})],
                                self.report,free_result_rows=free)["n"],0)
        self.assertEqual(extend({},[(self.key,{**self.original,
                                "home":"Liverpool"})],
                                self.report,free_result_rows=free)["n"],0)
        off=[{**row,"kickoff_utc":(self.kick+timedelta(hours=2)).isoformat()}
             for row in free]
        self.assertEqual(extend({},[(self.key,self.original)],
                                self.report,free_result_rows=off)["n"],0)

    def test_replay_uses_explicit_provenance_clock_and_bounded_file(self):
        free,diag=candidates(self.audit,self.now)
        self.assertEqual(len(free),1)
        self.assertEqual(diag["status"],"RESEARCH_ONLY")
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"archive.json"
            path.write_text(json.dumps(self.audit),encoding="utf-8")
            self.assertEqual(len(read_candidates(path,self.now)[0]),1)
            path.write_text("{partial",encoding="utf-8")
            self.assertEqual(read_candidates(path,self.now)[0],[])
            path.write_text("x"*500_001,encoding="utf-8")
            self.assertEqual(read_candidates(path,self.now)[0],[])


if __name__=="__main__":
    unittest.main()
