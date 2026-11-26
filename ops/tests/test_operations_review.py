import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from ops.operations_review import build,publish

NOW=datetime(2026,11,26,11,tzinfo=timezone.utc)
def doc(**kwargs):return {"production_recommendations":"DISABLED",**kwargs}
class OperationsReviewTests(unittest.TestCase):
    def test_missing_unknown_not_zero(self):
        r=build({},now=NOW)
        self.assertIsNone(r["counts"]["recorded_settled_research"])
        self.assertEqual(r["authenticated_forward_samples"],0)
        self.assertEqual(r["status"],"HOLD")
    def test_real_zero_separate_from_unknown_and_stale(self):
        r=build({"market_status":doc(matched_count=0,market_as_of_utc="2026-11-24T11:00:00Z")},now=NOW)
        self.assertEqual(r["counts"]["time_valid_market_pairs"],0)
        self.assertEqual(r["market_age_hours"],48)
        self.assertIn("MARKET_CLOCK_STALE_OR_FUTURE",[a["code"] for a in r["alerts"]])
    def test_mismatch_and_unsafe(self):
        r=build({"production_gate":doc(status="HOLD",model_promoted=False,settled_samples=2),
                 "forward_daily_scorecard":doc(settled_observations=3),
                 "quality":{"production_recommendations":"ENABLED","public_matches":99}},now=NOW)
        self.assertIsNone(r["counts"]["public_window_observations"])
        self.assertIn("SETTLED_REPORT_COUNT_MISMATCH",[a["code"] for a in r["alerts"]])
        self.assertFalse(r["automatic_bets"])
    def test_safe_publication_and_idempotent_nav(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);(p/"index.html").write_text("<html><body></body></html>")
            (p/"quality.json").write_text(json.dumps(doc(public_matches=2,secret="<script>bad</script>")))
            publish(p,now=NOW);publish(p,now=NOW)
            self.assertEqual((p/"index.html").read_text().count('id="operations-review-nav"'),1)
            self.assertNotIn("<script>bad</script>",(p/"operations-review.html").read_text())
            self.assertEqual(json.loads((p/"operations_review.json").read_text())["status"],"HOLD")
    def sidecars(self):
        ledger=doc(schema="football-king-global-full-slate-ledger-v1",generated_utc=NOW.isoformat(),
                   status="HOLD",global_coverage_complete=False,unique_global_match_count=None,
                   qualified_recommendations=0,rows=[doc(status="HOLD")],
                   counts={"input_rows":2,"retained_observations":1,"duplicate_observations":1,
                           "not_retained_due_to_bound":0,"in_window_observations":1,
                           "exact_core_model_reference_observations":0})
        market=doc(schema="football-king-unified-market-grid-v1",generated_utc=NOW.isoformat(),
                   status="RESEARCH_ONLY",actual_bookmaker_quotes=False,positive_ev_verified=False,
                   model_calibrated=False,recommendations=[],hypothetical_lines_only=True,
                   qualified_research_rows=1,rows=[doc(derived_grid={"asian_handicap":[{}]*82,"totals":[{}]*42})])
        return {"global_full_slate":ledger,"unified_market_grid":market}
    def test_integrated_counts_are_visible_and_not_recommendations(self):
        r=build(self.sidecars(),now=NOW)
        self.assertEqual(r["counts"]["full_slate_input_observations"],2)
        self.assertEqual(r["counts"]["full_slate_duplicate_observations"],1)
        self.assertEqual(r["counts"]["market_grid_hypothetical_line_directions"],124)
        self.assertFalse(r["positive_ev_verified"])
    def test_corrupt_sidecars_never_publish_counts(self):
        data=self.sidecars()
        data["global_full_slate"]["counts"]["input_rows"]=5
        data["unified_market_grid"]["rows"][0]["derived_grid"]["totals"]=[]
        r=build(data,now=NOW)
        self.assertIsNone(r["counts"]["full_slate_input_observations"])
        self.assertIsNone(r["counts"]["market_grid_research_rows"])
        self.assertEqual(r["source_states"]["global_full_slate"],"CONTRACT_REJECTED")
        self.assertEqual(r["source_states"]["unified_market_grid"],"CONTRACT_REJECTED")
    def test_stale_sidecar_and_malformed_summary_fail_closed(self):
        data=self.sidecars()
        data["global_full_slate"]["generated_utc"]="2026-11-25T00:00:00Z"
        data["forward_daily_scorecard"]=doc(error_review={"summary":[1]})
        r=build(data,now=NOW)
        self.assertIsNone(r["counts"]["full_slate_retained_observations"])
        self.assertIn("INVALID_ERROR_REVIEW_SUMMARY",[a["code"] for a in r["alerts"]])
        self.assertIsNone(r["descriptive_error_counts"]["observations"])
    def test_preserves_reconciliation_diagnostics_on_valid_grid(self):
        data=self.sidecars()
        data["global_full_slate"]["generated_utc"]="2026-11-24T11:00:00Z"
        data["unified_market_grid"]["output_bound_omissions"]=2
        data["forward_daily_scorecard"]=doc(settled_observations=1)
        data["research_center"]=doc(generated_utc=NOW.isoformat(),
            fourway_calibration_diagnostic=doc(diagnostic_input_validated=True,cohort_count=2))
        r=build(data,now=NOW)
        self.assertIsNone(r["counts"]["full_slate_retained_observations"])
        self.assertEqual(r["counts"]["market_grid_research_rows"],1)
        codes={a["code"] for a in r["alerts"]}
        self.assertIn("STALE_GLOBAL_FULL_SLATE",codes)
        self.assertIn("MARKET_GRID_OUTPUT_TRUNCATED",codes)
        self.assertIn("FOURWAY_COUNT_EXCEEDS_SETTLED",codes)
    def test_conflict_counters_cross_checked_with_rows(self):
        data=self.sidecars()
        ledger=data["global_full_slate"]
        ledger["rows"]=[doc(status="HOLD",reasons=["NATIVE_ID_OBSERVATION_CONFLICT"])]*2
        ledger["counts"].update(input_rows=2,retained_observations=2,
            duplicate_observations=0,conflicting_native_id_groups=1,conflicting_observations=2)
        r=build(data,now=NOW)
        self.assertEqual(r["counts"]["full_slate_conflicting_observations"],2)
        self.assertIn("NATIVE_ID_OBSERVATION_CONFLICTS",[a["code"] for a in r["alerts"]])
        ledger["counts"]["conflicting_observations"]=1
        r=build(data,now=NOW)
        self.assertIsNone(r["counts"]["full_slate_conflicting_observations"])
        self.assertEqual(r["source_states"]["global_full_slate"],"CONTRACT_REJECTED")
if __name__=="__main__":unittest.main()
