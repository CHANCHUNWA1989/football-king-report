import copy
import math
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import model_dixon_coles_forward as dc
from unified_dc_forward_audit import audit, archive_candidates, score_probability, paired_week_summary
from source_publish_guard import PROVIDERS, LEAGUES


class UnifiedDCForwardAuditTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,28,0,0,tzinfo=timezone.utc)
        pred="2026-11-27T10:00:00+00:00"
        self.kick="2026-11-27T14:00:00+00:00"
        h,a=1.4,1.1
        p=dc.probabilities(h,a,0.)
        self.base={"league":"epl","event_id":"test:1","home":"Everton","away":"Arsenal",
             "kickoff_utc":self.kick,"prediction_utc":pred,"model":dc.BASE_MODEL,
             "expected_home_goals":h,"expected_away_goals":a,
             "p_home":p[0],"p_draw":p[1],"p_away":p[2],
             "training_games":100,"training_cutoff_local_day":"2026-11-26",
             "training_observations_sha256":"a"*64,"production_recommendations":"DISABLED"}
        self.doc={"schema":"football-king-uncalibrated-shadow-1","status":"SHADOW_ONLY",
                  "production_recommendations":"DISABLED","as_of_utc":pred,
                  "predictions_count":1,"predictions":[self.base]}
        self.doc[dc.TOP_KEY]=dc.build(self.doc,now=datetime(2026,11,27,10,1,tzinfo=timezone.utc))
        self.assertEqual(len(self.doc[dc.TOP_KEY]["predictions"]),1)
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
                   "kickoff_utc":self.kick,"status":"FINISHED","score_ft":[1,1]})

    def run_case(self,docs=None):
        r=audit([self.doc] if docs is None else docs,self.sources,self.now)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["authenticated_forward_samples"],0)
        self.assertFalse(r["independent_oos_verified"])
        self.assertEqual(r["recommendation_count"],0)
        return r

    def test_same_fixture_paired_metrics(self):
        r=self.run_case()
        self.assertEqual(r["two_publisher_exact_score_candidate_count"],1)
        self.assertEqual(r["rows"][0]["score_ft"],[1,1])
        self.assertLess(r["metrics"]["candidate"]["log_loss"],r["metrics"]["derived_rho0"]["log_loss"])
        self.assertLess(r["metrics"]["candidate"]["score_log_loss"],r["metrics"]["derived_rho0"]["score_log_loss"])

    def test_missing_capture_not_reconstructed(self):
        del self.doc[dc.TOP_KEY]
        self.assertFalse(self.run_case()["rows"])

    def test_modified_candidate(self):
        self.doc[dc.TOP_KEY]["predictions"][0]["candidate"]=[.1,.8,.1]
        self.assertFalse(self.run_case()["rows"])

    def test_rate_tampering(self):
        self.base["expected_home_goals"]=1.5
        self.assertFalse(self.run_case()["rows"])

    def test_future_candidate(self):
        self.doc[dc.TOP_KEY]["generated_utc"]="2026-11-27T14:01:00+00:00"
        self.assertFalse(self.run_case()["rows"])

    def test_same_outcome_different_score(self):
        self.sources["sampled_fixtures"][1]["score_ft"]=[2,2]
        self.assertFalse(self.run_case()["rows"])

    def test_wrong_kickoff(self):
        self.sources["sampled_fixtures"][1]["kickoff_utc"]="2026-11-27T14:01:00+00:00"
        self.assertFalse(self.run_case()["rows"])

    def test_source_collection_before_match_finished(self):
        self.sources["started_utc"]="2026-11-27T14:30:00+00:00"
        self.sources["collected_utc"]="2026-11-27T14:40:00+00:00"
        self.assertFalse(self.run_case()["rows"])

    def test_identical_archives_count_once(self):
        self.assertEqual(len(self.run_case([self.doc,copy.deepcopy(self.doc)])["rows"]),1)

    def test_conflicting_earliest_capture(self):
        other=copy.deepcopy(self.doc)
        other["predictions"][0]["training_observations_sha256"]="b"*64
        other[dc.TOP_KEY]=dc.build(other,now=datetime(2026,11,27,10,1,tzinfo=timezone.utc))
        self.assertFalse(self.run_case([self.doc,other])["rows"])

    def test_event_id_reused_across_archives_quarantines_both(self):
        other=copy.deepcopy(self.doc)
        other["predictions"][0]["kickoff_utc"]="2026-11-27T15:00:00+00:00"
        other[dc.TOP_KEY]=dc.build(other,now=datetime(2026,11,27,10,1,tzinfo=timezone.utc))
        r=self.run_case([self.doc,other])
        self.assertFalse(r["rows"])
        self.assertEqual(r["rejected"]["CROSS_ARCHIVE_EVENT_ID_CONFLICT"],2)

    def test_week_summary_uses_paired_same_fixture_losses(self):
        r=self.run_case()
        summary=r["paired_week_summary"]
        self.assertEqual(summary["n"],1)
        self.assertEqual(summary["week_blocks"],1)
        self.assertEqual(summary["leagues"],{"epl":1})
        self.assertAlmostEqual(summary["paired_mean_log_loss_improvement"],
            r["metrics"]["derived_rho0"]["log_loss"]-r["metrics"]["candidate"]["log_loss"])
        self.assertIsNone(summary["confidence_interval"])
        self.assertFalse(summary["significance_claim_permitted"])

    def test_empty_week_summary_no_implied_improvement(self):
        r=paired_week_summary([])
        self.assertEqual(r["n"],0)
        self.assertIsNone(r["paired_mean_log_loss_improvement"])
        self.assertIsNone(r["confidence_interval"])

    def test_score_support_and_normalization(self):
        self.assertIsNone(score_probability(1.4,1.1,0.,12,0))
        for rho in (0.,dc.RHO):
            self.assertAlmostEqual(math.fsum(score_probability(1.4,1.1,rho,i,j) for i in range(12) for j in range(12)),1)

if __name__=="__main__":
    unittest.main()
