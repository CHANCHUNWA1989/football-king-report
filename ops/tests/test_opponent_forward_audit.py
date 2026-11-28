import copy
import unittest
from datetime import date,datetime,timedelta,timezone
from ops.shadow_forecast import predict_league
from ops.opponent_forward_capture import capture,attach,TOP_KEY
from ops.opponent_forward_audit import audit
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


if __name__=="__main__":
    unittest.main()
