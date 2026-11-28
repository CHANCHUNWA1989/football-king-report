import copy
import unittest
from unittest.mock import patch
from ops import opponent_forward_audit as audit_module
from datetime import date,datetime,timedelta,timezone
from ops.shadow_forecast import predict_league
from ops.opponent_forward_capture import capture,attach,TOP_KEY
from ops.opponent_forward_audit import audit,german_final_votes,archived_result_snapshots
import gzip
import json
import tempfile
from pathlib import Path
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

    def test_same_publisher_two_native_ids_same_score_is_ambiguous(self):
        row=copy.deepcopy(self.sources["sampled_fixtures"][0])
        row["provider_event_id"]="another-native-id"
        self.sources["sampled_fixtures"].append(row)
        p=self.sources["providers"][0]
        p["sampled_fixture_count"]+=1
        p["counts_by_league"]["epl"]+=1
        result=self.run_case()
        self.assertFalse(result["rows"])
        self.assertEqual(result["rejected"]["AMBIGUOUS_PROVIDER_FIXTURE_ID"],1)

    def test_changed_native_id_across_snapshots_is_ambiguous(self):
        old=copy.deepcopy(self.sources)
        old["sampled_fixtures"][0]["provider_event_id"]="previous-id"
        result=audit([self.doc],self.sources,self.now,source_history=[old])
        self.assertFalse(result["rows"])
        self.assertEqual(result["rejected"]["AMBIGUOUS_PROVIDER_FIXTURE_ID"],1)

    def test_same_native_id_across_snapshots_remains_valid(self):
        old=copy.deepcopy(self.sources)
        old["sampled_fixtures"][0]["status"]="SCHEDULED"
        old["sampled_fixtures"][0]["score_ft"]=None
        result=audit([self.doc],self.sources,self.now,source_history=[old])
        self.assertEqual(result["two_publisher_exact_score_count"],1)
        self.assertEqual(result["authenticated_forward_samples"],0)

    def test_pinned_cohort_retains_23_day_old_postmatch_observations(self):
        old=copy.deepcopy(self.sources)
        now=self.now+timedelta(days=23)
        current=copy.deepcopy(self.sources)
        current["started_utc"]=(now-timedelta(minutes=15)).isoformat()
        current["collected_utc"]=(now-timedelta(minutes=10)).isoformat()
        current["sampled_fixtures"]=[]
        for p in current["providers"]:
            p["sampled_fixture_count"]=0
            p["counts_by_league"]={l:0 for l in LEAGUES}
        default=audit([self.doc],current,now,source_history=[old])
        self.assertEqual(default["two_publisher_exact_score_count"],0)
        extended=audit([self.doc],current,now,source_history=[old],extended_history=True)
        self.assertEqual(extended["two_publisher_exact_score_count"],1)
        self.assertEqual(extended["result_history_max_age_days"],35)
        self.assertEqual(extended["result_history_scan_limit"],120)
        self.assertEqual(extended["authenticated_forward_samples"],0)
        self.assertEqual(extended["production_recommendations"],"DISABLED")
        # Historical data is never a replacement for a fresh latest source.
        stale=audit([self.doc],old,now,source_history=[old],extended_history=True)
        self.assertEqual(stale["reason"],"NO_VALID_RESULT_SOURCE")

    def test_pinned_history_still_rejects_36_day_old_observation(self):
        old=copy.deepcopy(self.sources)
        now=self.now+timedelta(days=36)
        current=copy.deepcopy(self.sources)
        current["started_utc"]=(now-timedelta(minutes=15)).isoformat()
        current["collected_utc"]=(now-timedelta(minutes=10)).isoformat()
        current["sampled_fixtures"]=[]
        for p in current["providers"]:
            p["sampled_fixture_count"]=0
            p["counts_by_league"]={l:0 for l in LEAGUES}
        r=audit([self.doc],current,now,source_history=[old],extended_history=True)
        self.assertFalse(r["rows"])
        self.assertEqual(r["valid_result_history_snapshots"],0)

    def test_pinned_history_reader_is_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            folder=root/"2026"/"11"/"28"
            folder.mkdir(parents=True)
            for i in range(125):
                with gzip.open(folder/f"{i:03}.json.gz","wb") as f:
                    f.write(json.dumps({"index":i}).encode())
            self.assertEqual(len(archived_result_snapshots(root)),70)
            rows=archived_result_snapshots(root,extended=True)
            self.assertEqual(len(rows),120)
            self.assertEqual(rows[0]["index"],124)
            self.assertEqual(rows[-1]["index"],5)

    def test_pinned_only_cli_excludes_local_archive_forecasts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            archives=root/"archives"
            archives.mkdir()
            with gzip.open(archives/"unrelated.json.gz","wb") as f:
                f.write(json.dumps(self.doc).encode())
            source=root/"source.json"
            source.write_text(json.dumps(self.sources))
            output=root/"audit.json"
            argv=["audit","--archives",str(archives),"--sources",str(source),
                  "--output",str(output),"--research-artifact","pinned.zip",
                  "--artifact-sha256","a"*64,"--artifact-run-id","123","--artifact-attempt","1"]
            verified=([self.doc],[{"candidate_count":1}])
            with patch("sys.argv",argv+["--pinned-only"]), patch.object(audit_module,"verified_artifacts",return_value=verified):
                audit_module.main()
            pinned=json.loads(output.read_text())
            self.assertEqual(pinned["forecast_scope"],"PINNED_ARTIFACTS_ONLY")
            self.assertEqual(pinned["archive_documents_scanned"],1)
            self.assertEqual(pinned["candidate_observations"],1)
            self.assertEqual(pinned["readonly_artifact_unique_fixture_count"],1)
            with patch("sys.argv",argv), patch.object(audit_module,"verified_artifacts",return_value=verified):
                audit_module.main()
            mixed=json.loads(output.read_text())
            self.assertEqual(mixed["candidate_observations"],2)
            self.assertEqual(mixed["forecast_scope"],"LOCAL_ARCHIVES_AND_EXPLICIT_ARTIFACTS")
            self.assertEqual(pinned["authenticated_forward_samples"],0)

    def test_pinned_only_requires_explicit_artifact(self):
        with patch("sys.argv",["audit","--archives","unused","--sources","unused","--output","unused","--pinned-only"]):
            with self.assertRaises(SystemExit) as exc:
                audit_module.main()
            self.assertEqual(exc.exception.code,2)

    def test_three_model_same_source_capture_and_shared_result(self):
        r=self.doc[TOP_KEY]["predictions"][0]
        dc={"league":r["league"],"event_id":r["event_id"],"home":r["home"],
            "away":r["away"],"kickoff_utc_recorded":r["kickoff_utc"],
            "source_prediction_utc":r["original_prediction_utc"],
            "prediction_utc":r["candidate_prediction_utc"],"original":r["original"],
            "derived_rho0":r["original"],"candidate":[.3,.4,.3]}
        # DC archive validation is independently covered by its own tests.
        with patch.object(audit_module,"dc_candidates",return_value=[dc]):
            report=self.run_case()
        paired=report["three_model_comparison"]
        self.assertEqual(paired["n"],1)
        self.assertEqual(paired["paired_rows"][0]["score_ft"],[1,1])
        self.assertEqual(set(paired["metrics"]),{"original","opponent","dc","dc_derived_rho0"})
        self.assertEqual(paired["metrics"]["dc"]["hits"],1)
        self.assertFalse(paired["independent_oos_verified"])
        self.assertEqual(report["three_model_forecast_coverage"]["three_model_ready"],1)
        self.assertEqual(paired["excluded_settled_n"],0)
        with patch.object(audit_module,"dc_candidates",return_value=[dc]):
            no_results=audit([self.doc],None,self.now)
        self.assertEqual(no_results["three_model_forecast_coverage"],report["three_model_forecast_coverage"])
        self.assertEqual(no_results["three_model_comparison"]["n"],0)

    def test_three_model_missing_or_mismatched_dc_does_not_backfill(self):
        r=self.doc[TOP_KEY]["predictions"][0]
        dc={"league":r["league"],"event_id":r["event_id"],"home":r["home"],
            "away":r["away"],"kickoff_utc_recorded":r["kickoff_utc"],
            "source_prediction_utc":"2026-11-27T10:02:00+00:00",
            "prediction_utc":r["candidate_prediction_utc"],"original":r["original"],
            "derived_rho0":r["original"],"candidate":[.3,.4,.3]}
        for supplied in ([],[dc]):
            with patch.object(audit_module,"dc_candidates",return_value=supplied):
                report=self.run_case()
            self.assertEqual(report["two_publisher_exact_score_count"],1)
            self.assertEqual(report["three_model_comparison"]["n"],0)
            self.assertIsNone(report["three_model_comparison"]["metrics"])
            self.assertEqual(report["three_model_comparison"]["excluded_settled_n"],1)
            self.assertEqual(report["three_model_forecast_coverage"]["not_ready"],1)

    def test_conflicting_dc_duplicate_is_reported_before_results(self):
        r=self.doc[TOP_KEY]["predictions"][0]
        dc={"league":r["league"],"event_id":r["event_id"],"home":r["home"],
            "away":r["away"],"kickoff_utc_recorded":r["kickoff_utc"],
            "source_prediction_utc":r["original_prediction_utc"],
            "prediction_utc":r["candidate_prediction_utc"],"original":r["original"],
            "derived_rho0":r["original"],"candidate":[.3,.4,.3]}
        other=dict(dc,candidate=[.4,.3,.3])
        with patch.object(audit_module,"dc_candidates",side_effect=[[dc],[other]]):
            report=audit([self.doc,copy.deepcopy(self.doc)],None,self.now)
        coverage=report["three_model_forecast_coverage"]
        self.assertEqual(coverage["unique_fixtures"],1)
        self.assertEqual(coverage["three_model_ready"],0)
        self.assertEqual(coverage["by_league"]["epl"]["dc_missing_or_conflicting"],1)
        self.assertFalse(coverage["uses_result_labels"])

    def test_fixed_calibration_bins_and_class_bias(self):
        rows=[{"p":[.2,.4,.4],"y":1},{"p":[.8,.2,0.],"y":0},
              {"p":[0.,0.,1.],"y":2}]
        r=audit_module.calibration_diagnostics(rows,"p")
        self.assertEqual(r["n"],3)
        self.assertTrue(r["descriptive_only"])
        self.assertFalse(r["probabilities_adjusted"])
        home=r["classes"]["home"]
        self.assertEqual([b["n"] for b in home["bins"]],[1,1,0,0,1])
        self.assertAlmostEqual(home["signed_probability_bias"],0.)
        self.assertAlmostEqual(home["class_brier"],(.2**2+.2**2)/3)
        self.assertAlmostEqual(home["fixed_bin_ece"],.4/3)
        self.assertIsNone(home["bins"][2]["observed_fraction"])
        away=r["classes"]["away"]
        self.assertEqual(away["bins"][-1]["n"],1)
        self.assertEqual(away["bins"][-1]["mean_probability"],1.)

    def test_empty_calibration_has_no_implied_skill(self):
        r=audit_module.three_model_summary([])
        self.assertIsNone(r["metrics"])
        for diag in r["calibration_diagnostics"].values():
            self.assertEqual(diag["n"],0)
            for cls in diag["classes"].values():
                self.assertIsNone(cls["signed_probability_bias"])
                self.assertIsNone(cls["class_brier"])
                self.assertIsNone(cls["fixed_bin_ece"])
                self.assertEqual(sum(b["n"] for b in cls["bins"]),0)

    def test_paired_uncertainty_small_sample_has_no_interval(self):
        row={"league":"epl","kickoff_utc":"2026-11-27T14:00:00+00:00",
             "y":0,"a":[.4,.3,.3],"b":[.5,.25,.25]}
        r=audit_module.paired_uncertainty([row],"a","b")
        self.assertGreater(r["log_loss_gain"],0)
        self.assertGreater(r["brier_gain"],0)
        self.assertIsNone(r["descriptive_week_resampling_interval"])
        self.assertFalse(r["significance_claim_permitted"])
        self.assertFalse(any(r["coverage_gates"].values()))

    def test_week_block_resampling_fixed_protocol_and_coverage(self):
        start=datetime(2026,1,5,tzinfo=timezone.utc)
        leagues=("epl","bundesliga","seriea","laliga")
        rows=[{"league":leagues[i%4],"kickoff_utc":(start+timedelta(weeks=i//25)).isoformat(),
               "y":0,"a":[.4,.3,.3],"b":[.5,.25,.25]} for i in range(300)]
        r=audit_module.paired_uncertainty(rows,"a","b")
        self.assertTrue(all(r["coverage_gates"].values()))
        self.assertEqual(r["week_blocks"],12)
        self.assertEqual(r,audit_module.paired_uncertainty(rows,"a","b"))
        for v in r["descriptive_week_resampling_interval"]["log_loss_gain"]:
            self.assertAlmostEqual(v,r["log_loss_gain"])
        self.assertIsNone(r["confidence_interval"])
        self.assertFalse(r["independent_oos_verified"])
        self.assertFalse(r["significance_claim_permitted"])
        # A large sample concentrated in a single week is insufficient.
        concentrated=[dict(x,kickoff_utc=start.isoformat()) for x in rows]
        self.assertIsNone(audit_module.paired_uncertainty(concentrated,"a","b")["descriptive_week_resampling_interval"])


if __name__=="__main__":
    unittest.main()
