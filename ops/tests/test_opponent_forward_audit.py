import copy
import unittest
from datetime import date,datetime,timedelta,timezone
from ops.shadow_forecast import predict_league
from ops.opponent_forward_capture import capture,attach,TOP_KEY
from ops.opponent_forward_audit import audit,german_final_votes
from ops.source_publish_guard import PROVIDERS,LEAGUES


class OpponentForwardAuditTest(unittest.TestCase):
    def setUp(self):
        start=datetime(2026,11,27,10,tzinfo=timezone.utc)
        self.now=datetime(2026,11,28,0,tzinfo=timezone.utc)
        kick="2026-11-27T14:00:00+00:00"
        rows=[]
        for i in range(60):
            d=date.fromordinal(date(2026,8,1).toordinal()+i)
            h,a=("Everton","Arsenal") if i%2==0 else ("Arsenal","Everton")
            rows.append({"league":"epl","date":d.isoformat(),"home":h,"away":a,
                         "score_ft":[2,1],"status":"FINISHED"})
        future={"date":"2026-11-27","home":"Everton","away":"Arsenal","status":"SCHEDULED",
                "event_id":"test:1","kickoff_utc":kick}
        preds=predict_league(rows+[future],"epl",start)
        base={"schema":"football-king-uncalibrated-shadow-1","status":"SHADOW_ONLY",
              "production_recommendations":"DISABLED","as_of_utc":start.isoformat(),
              "predictions_count":len(preds),"predictions":preds}
        finished={"schema":"football-king-single-source-finished-results-1",
                  "captured_utc":start.isoformat(),"production_recommendations":"DISABLED","records":rows}
        clock=iter([start,start+timedelta(minutes=1)])
        self.doc=attach(base,capture(base,finished,lambda:next(clock)))
        self.assertEqual(self.doc[TOP_KEY]["predictions_count"],1)
        self.sources={"schema":"football-king-extra-source-audit-v1",
           "production_recommendations":"DISABLED","six_league_independent_results_verified":False,
           "odds_fallback_confirmed":False,"coverage_is_complete":False,
           "original_api_payload_redistributed":False,
           "started_utc":"2026-11-27T23:45:00+00:00","collected_utc":"2026-11-27T23:50:00+00:00",
           "providers":[],"sampled_fixtures":[]}
        for i,provider in enumerate(PROVIDERS):
            n=int(i<2)
            self.sources["providers"].append({"provider":provider,"status":"PARTIAL",
              "configured":True,"production_recommendations":"DISABLED",
              "can_replace_1x2_market":False,"original_bookmaker_odds_redistributed":False,
              "league_result_verification_complete":False,"calls_attempted":n,
              "sampled_fixture_count":n,"counts_by_league":{l:n if l=="epl" else 0 for l in LEAGUES}})
            if n:
                self.sources["sampled_fixtures"].append({"provider":provider,"league":"epl",
                   "provider_event_id":str(i),"home":"Everton","away":"Arsenal",
                   "kickoff_utc":kick,"status":"FINISHED","score_ft":[1,1]})

    def run_case(self,docs=None):
        r=audit([self.doc] if docs is None else docs,self.sources,self.now)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["authenticated_forward_samples"],0)
        self.assertFalse(r["independent_oos_verified"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["recommendation_count"],0)
        return r
    def test_pair_and_deduplicate(self):
        r=self.run_case([self.doc,copy.deepcopy(self.doc)])
        self.assertEqual(r["two_publisher_exact_score_count"],1)
        self.assertEqual(r["rows"][0]["score_ft"],[1,1])
        self.assertEqual(r["metrics"]["candidate"]["n"],1)
        self.assertEqual(r["metrics"]["original"]["n"],1)
    def test_no_backfill(self):
        del self.doc[TOP_KEY]
        self.assertFalse(self.run_case()["rows"])
    def test_conflicting_score(self):
        self.sources["sampled_fixtures"][1]["score_ft"]=[2,2]
        self.assertFalse(self.run_case()["rows"])
    def test_tampered_probability(self):
        self.doc[TOP_KEY]["predictions"][0]["p"]=[.1,.8,.1]
        self.assertFalse(self.run_case()["rows"])
    def test_wrong_kickoff(self):
        self.sources["sampled_fixtures"][1]["kickoff_utc"]="2026-11-27T14:01:00+00:00"
        self.assertFalse(self.run_case()["rows"])
    def test_early_result(self):
        self.sources["started_utc"]="2026-11-27T14:30:00+00:00"
        self.sources["collected_utc"]="2026-11-27T14:40:00+00:00"
        self.assertFalse(self.run_case()["rows"])


    def test_german_source_requires_post_match_collection_start(self):
        report={"schema":"football-king-openligadb-hourly-v1","source":"OpenLigaDB",
                "source_type":"COMMUNITY_CONTRIBUTED_NOT_OFFICIAL_LIVE","status":"RESEARCH_ONLY",
                "production_recommendations":"DISABLED","six_league_results_independently_verified":False,
                "replaces_bookmaker_market":False,"used_to_refit_model":False,
                "started_utc":"2026-11-27T23:40:00+00:00","collected_utc":"2026-11-27T23:41:00+00:00",
                "matches":[{"league":"bundesliga","home":"Werder Bremen","away":"Borussia Mönchengladbach",
                  "provider_match_id":123,"kickoff_utc":"2026-11-27T19:30:00+00:00",
                  "status":"FINISHED_CONFIRMED_BY_SOURCE","score_ft":[3,3]}]}
        votes=german_final_votes(report,self.now)
        self.assertEqual(len(votes),1)
        self.assertEqual(next(iter(votes.values())),{(3,3)})
        bad=copy.deepcopy(report)
        del bad["started_utc"]
        self.assertFalse(german_final_votes(bad,self.now))
        bad=copy.deepcopy(report)
        bad["matches"][0]["status"]="STARTED_STATUS_UNCONFIRMED"
        self.assertFalse(german_final_votes(bad,self.now))
        bad=copy.deepcopy(report)
        bad["started_utc"]="2026-11-27T20:00:00+00:00"
        bad["collected_utc"]="2026-11-27T20:01:00+00:00"
        self.assertFalse(german_final_votes(bad,self.now))
        bad=copy.deepcopy(report)
        bad["matches"].append(dict(bad["matches"][0],kickoff_utc="2026-11-27T19:31:00+00:00"))
        self.assertFalse(german_final_votes(bad,self.now))

    def test_earlier_result_archive_recovers_second_publisher(self):
        history=copy.deepcopy(self.sources)
        old=copy.deepcopy(self.sources)
        # The later snapshot retained only TheSportsDB; the other publisher
        # was observed in a prior valid post-match snapshot.
        old["sampled_fixtures"].pop()
        p=old["providers"][1]
        p["sampled_fixture_count"]=0
        p["counts_by_league"]={l:0 for l in LEAGUES}
        self.assertFalse(audit([self.doc],old,self.now)["rows"])
        result=audit([self.doc],old,self.now,source_history=[history])
        self.assertEqual(result["two_publisher_exact_score_count"],1)
        self.assertEqual(result["valid_result_history_snapshots"],1)
        self.assertEqual(result["authenticated_forward_samples"],0)

    def test_archived_score_conflict_blocks_settlement(self):
        old=copy.deepcopy(self.sources)
        old["sampled_fixtures"][0]["score_ft"]=[2,2]
        result=audit([self.doc],self.sources,self.now,source_history=[old])
        self.assertFalse(result["rows"])
        self.assertEqual(result["rejected"]["CONFLICTING_FINAL_SCORES"],1)

    def test_archived_native_id_reuse_blocks_settlement(self):
        old=copy.deepcopy(self.sources)
        old["sampled_fixtures"][0]["kickoff_utc"]="2026-11-27T14:01:00+00:00"
        result=audit([self.doc],self.sources,self.now,source_history=[old])
        self.assertFalse(result["rows"])
        self.assertEqual(result["rejected"]["RESULT_SOURCE_NATIVE_ID_CONFLICT"],1)

    def test_pre_match_archive_not_admitted_as_result(self):
        old=copy.deepcopy(self.sources)
        old["started_utc"]="2026-11-27T14:30:00+00:00"
        old["collected_utc"]="2026-11-27T14:40:00+00:00"
        old["sampled_fixtures"][0]["score_ft"]=[9,9]
        result=audit([self.doc],self.sources,self.now,source_history=[old])
        self.assertEqual(result["two_publisher_exact_score_count"],1)
        self.assertEqual(result["rows"][0]["score_ft"],[1,1])


if __name__=="__main__":
    unittest.main()
