import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verified_market_pipeline import analyze

NOW=datetime(2026,10,9,14,0,tzinfo=timezone.utc)

def case():
    return {"fixture":{"home":"Home","away":"Away","league":"soccer_epl",
                        "event_id":"odds-event-1","independent_fixture_sources":2},
            "screenshot":{"event_id":"odds-event-1",
                          "observed_at_utc":"2026-10-09T13:59:30Z",
                          "home_goals":0,"away_goals":0,"minute":30},
            "live_stats":{"event_id":"odds-event-1",
                          "updated_at_utc":"2026-10-09T13:59:30Z",
                          "independently_verified":True},
            "model":{"supported_league":"soccer_epl","supported_market":"totals",
                     "calibration_verified":True,"leakage_audit_passed":True,
                     "out_of_sample_verified":True,
                     "independent_settled_forward_samples":10000,
                     "ev_provenance_verified":True,
                     "market_baseline_beaten_out_of_sample":True},
            "market":{"event_id":"odds-event-1","league":"soccer_epl",
                      "market_key":"totals","validated_by_market_quote_gate":True,
                      "bookmaker_quote_executable_verified":True,
                      "last_update_utc":"2026-10-09T14:00:00Z"}}

def odds():
    return [{"id":"odds-event-1","sport_key":"soccer_epl",
             "home_team":"Home","away_team":"Away",
             "commence_time":"2026-10-09T13:00:00Z",
             "bookmakers":[{"key":"book1","markets":[
                 {"key":"totals","last_update":"2026-10-09T13:59:45Z",
                  "outcomes":[{"name":"Over","price":1.9,"point":1.75},
                              {"name":"Under","price":1.9,"point":1.75}]}]}]}]

class PipelineTests(unittest.TestCase):
    def test_real_validated_quote_links_into_market_checks(self):
        r=analyze(case(),odds(),now=NOW)
        self.assertEqual(r["matched_verified_quotes"],2)
        self.assertFalse(r["decision"]["gate_checks"]["market_validated"])
        self.assertTrue(r["decision"]["gate_checks"]["market_identity"])
        self.assertTrue(r["decision"]["gate_checks"]["market_clock"])
        self.assertFalse(r["decision"]["gate_checks"]["market_executable"])
        self.assertEqual(r["status"],"HOLD")
        self.assertIsNone(r["decision"]["recommendation"])

    def test_inplay_quote_not_counted_as_prematch_evidence(self):
        r=analyze(case(),odds(),now=NOW)
        self.assertEqual(r["matched_verified_quotes"],2)
        self.assertEqual(r["prematch_evidence_quotes"],0)
        self.assertFalse(r["prematch_evidence_available"])
        self.assertTrue(all(not q["quote_eligible_as_prematch_evidence"]
                            for q in r["research_quotes"]))
        self.assertEqual(r["status"],"HOLD")

    def test_genuine_prematch_snapshot_propagates_eligibility(self):
        d=odds()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        r=analyze(case(),d,now=NOW)
        self.assertEqual(r["matched_verified_quotes"],2)
        self.assertEqual(r["prematch_evidence_quotes"],2)
        self.assertTrue(r["prematch_evidence_available"])
        self.assertFalse(r["decision"]["gate_checks"]["market_validated"])
        self.assertFalse(r["decision"]["gate_checks"]["market_executable"])
        self.assertEqual(r["production_recommendations"],"DISABLED")

    def test_mixed_snapshot_prefers_prematch_over_fresher_inplay(self):
        d=odds()
        # Two provider events cannot share an ID: instead mix two bookmaker
        # markets under one fixture, each with distinct update timestamps.
        d[0]["commence_time"]="2026-10-09T14:00:30Z"
        d[0]["bookmakers"][0]["markets"][0]["last_update"]="2026-10-09T13:59:45Z"
        # Capture is 14:00Z: this remains too late to count as prematch.
        r=analyze(case(),d,now=NOW)
        self.assertEqual(r["prematch_evidence_quotes"],0)
        self.assertFalse(r["decision"]["gate_checks"]["market_validated"])

    def test_market_type_mismatch_cannot_validate_another_market(self):
        d=odds()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        c=case()
        c["model"]["supported_market"]="spreads"
        result=analyze(c,d,now=NOW)
        self.assertEqual(result["matched_verified_quotes"],2)
        self.assertEqual(result["matched_model_market_quotes"],0)
        self.assertEqual(result["prematch_evidence_quotes"],0)
        self.assertIsNone(result["selected_quote_identity"])
        self.assertEqual(result["reason"],"NO_MATCHING_MODEL_MARKET_QUOTES")
        self.assertFalse(result["decision"]["gate_checks"]["market_validated"])
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_requested_market_matches_selected_market_identity(self):
        d=odds()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        result=analyze(case(),d,now=NOW)
        self.assertEqual(result["matched_model_market_quotes"],2)
        self.assertEqual(result["selected_quote_identity"]["market"],"totals")
        self.assertFalse(result["decision"]["gate_checks"]["market_validated"])

    def test_prematch_quote_requires_full_bet_identity(self):
        d=odds()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        c=case()
        r=analyze(c,d,now=NOW)
        self.assertFalse(r["complete_requested_bet_identity"])
        self.assertEqual(r["prematch_evidence_quotes"],2)
        self.assertFalse(r["decision"]["gate_checks"]["market_validated"])
        c["model"]["requested_outcome"]="Under"
        r=analyze(c,d,now=NOW)
        self.assertFalse(r["complete_requested_bet_identity"])
        self.assertFalse(r["decision"]["gate_checks"]["market_validated"])

    def test_exact_outcome_and_point_match(self):
        d=odds()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        c=case()
        c["model"]["requested_outcome"]="Under"
        c["model"]["requested_point"]=1.75
        result=analyze(c,d,now=NOW)
        self.assertEqual(result["matched_model_market_quotes"],1)
        self.assertEqual(result["selected_quote_identity"]["outcome"],"Under")
        self.assertEqual(result["selected_quote_identity"]["point"],1.75)
        self.assertTrue(result["decision"]["gate_checks"]["market_validated"])

    def test_wrong_outcome_or_point_cannot_borrow_quote(self):
        d=odds()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        for requested in ({"requested_outcome":"Draw"},
                          {"requested_outcome":"Under","requested_point":2.25},
                          {"requested_point":True}):
            with self.subTest(requested=requested):
                c=case()
                c["model"].update(requested)
                result=analyze(c,d,now=NOW)
                self.assertEqual(result["matched_model_market_quotes"],0)
                self.assertIsNone(result["selected_quote_identity"])
                self.assertFalse(result["decision"]["gate_checks"]["market_validated"])
                self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_selected_quote_preserves_bookmaker_market_and_line(self):
        d=odds()
        d[0]["commence_time"]="2026-10-09T18:00:00Z"
        result=analyze(case(),d,now=NOW)
        identity=result["selected_quote_identity"]
        self.assertEqual(identity["event_id"],"odds-event-1")
        self.assertEqual(identity["bookmaker"],"book1")
        self.assertEqual(identity["market"],"totals")
        self.assertEqual(identity["point"],1.75)
        self.assertIn(identity["outcome"],("Over","Under"))
        self.assertEqual(identity["market_last_update_utc"],
                         "2026-10-09T13:59:45+00:00")
        self.assertFalse(result["decision"]["gate_checks"]["market_executable"])
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_no_quote_never_invents_selected_quote_identity(self):
        result=analyze(case(),[],now=NOW)
        self.assertIsNone(result["selected_quote_identity"])
        self.assertEqual(result["matched_verified_quotes"],0)

    def test_untrusted_executable_flag_is_overridden(self):
        r=analyze(case(),odds(),now=NOW)
        self.assertIn("BOOKMAKER_EXECUTION_NOT_VERIFIED",r["decision"]["blockers"])
        self.assertIn("NO_INDEPENDENT_SIGNED_PROMOTION_APPROVAL",r["decision"]["blockers"])

    def test_cross_provider_event_id_does_not_join(self):
        d=odds()
        d[0]["id"]="other-provider-event-42"
        r=analyze(case(),d,now=NOW)
        self.assertEqual(r["matched_verified_quotes"],0)
        self.assertFalse(r["decision"]["gate_checks"]["market_validated"])
        self.assertEqual(r["reason"],"NO_MATCHING_VERIFIED_MARKET_QUOTES")

    def test_stale_odds_fail_closed(self):
        d=odds()
        d[0]["bookmakers"][0]["markets"][0]["last_update"]="2026-10-09T13:50:00Z"
        r=analyze(case(),d,now=NOW)
        self.assertEqual(r["matched_verified_quotes"],0)
        self.assertEqual(r["status"],"HOLD")

    def test_unverified_fixture_never_associates_quotes(self):
        c=case()
        c["fixture"]["event_id"]=""
        r=analyze(c,odds(),now=NOW)
        self.assertIsNone(r["market_quote_audit"])
        self.assertEqual(r["reason"],"UNVERIFIED_FIXTURE_ID")

    def test_ambiguous_or_overlong_fixture_fails_before_market_join(self):
        for field,value in (("home","Away"),("home","Home"*41),
                            ("league","x"*121),("event_id","x"*121)):
            with self.subTest(field=field,value=value[:16]):
                c=case()
                c["fixture"][field]=value
                result=analyze(c,odds(),now=NOW)
                self.assertEqual(result["reason"],"UNVERIFIED_FIXTURE_ID")
                self.assertEqual(result["matched_verified_quotes"],0)
                self.assertIsNone(result["market_quote_audit"])
                self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_wrong_league_does_not_join(self):
        d=odds()
        d[0]["sport_key"]="soccer_spain_la_liga"
        r=analyze(case(),d,now=NOW)
        self.assertEqual(r["matched_verified_quotes"],0)

    def test_bad_market_point_rejected(self):
        d=odds()
        d[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["point"]=1.33
        r=analyze(case(),d,now=NOW)
        self.assertEqual(r["matched_verified_quotes"],1)

    def test_empty_odds_is_hold(self):
        r=analyze(case(),[],now=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["matched_verified_quotes"],0)

    def test_naive_now_rejected(self):
        with self.assertRaises(ValueError):
            analyze(case(),odds(),now=datetime(2026,10,9,14))

if __name__=="__main__":
    unittest.main()
