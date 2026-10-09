import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unified_match_gate import evaluate

NOW=datetime(2026,10,9,14,0,0,tzinfo=timezone.utc)
def complete():
    return {
      "fixture":{"home":"Home","away":"Away","league":"soccer_epl",
                 "event_id":"event-1","independent_fixture_sources":2},
      "screenshot":{"event_id":"event-1","observed_at_utc":"2026-10-09T13:59:30Z",
                    "home_goals":0,"away_goals":0,"minute":30.5},
      "live_stats":{"event_id":"event-1","updated_at_utc":"2026-10-09T13:59:10Z",
                    "independently_verified":True},
      "market":{"event_id":"event-1","league":"soccer_epl",
                "market_key":"totals","last_update_utc":"2026-10-09T13:59:45Z",
                "validated_by_market_quote_gate":True,
                "bookmaker_quote_executable_verified":True},
      "model":{"supported_league":"soccer_epl","supported_market":"totals",
               "calibration_verified":True,"leakage_audit_passed":True,
               "out_of_sample_verified":True,
               "independent_settled_forward_samples":300,
               "ev_provenance_verified":True,
               "market_baseline_beaten_out_of_sample":True},
    }

class UnifiedMatchGateTests(unittest.TestCase):
    def test_even_perfect_user_claims_do_not_unlock_wagers(self):
        r=evaluate(complete(),now=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["can_execute_bet"])
        self.assertFalse(r["can_publish_pick"])
        self.assertIsNone(r["recommendation"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["blockers"],["NO_INDEPENDENT_SIGNED_PROMOTION_APPROVAL"])

    def test_missing_inputs_fail_closed(self):
        r=evaluate({},now=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["checks_passed"],0)
        self.assertGreaterEqual(len(r["blockers"]),12)

    def test_stale_screenshot_does_not_borrow_current_market(self):
        c=complete()
        c["screenshot"]["observed_at_utc"]="2026-10-09T13:30:00Z"
        r=evaluate(c,now=NOW)
        self.assertIn("SCREENSHOT_STALE_OR_MISSING_CLOCK",r["blockers"])
        self.assertTrue(r["gate_checks"]["market_clock"])

    def test_stale_market_blocks_even_when_screenshot_fresh(self):
        c=complete()
        c["market"]["last_update_utc"]="2026-10-09T13:50:00Z"
        r=evaluate(c,now=NOW)
        self.assertIn("MARKET_QUOTE_STALE_OR_MISSING",r["blockers"])

    def test_cross_match_market_is_rejected(self):
        c=complete()
        c["market"]["event_id"]="different-match"
        self.assertIn("MARKET_FIXTURE_OR_LEAGUE_MISMATCH",
                      evaluate(c,now=NOW)["blockers"])

    def test_unverified_xg_never_passes(self):
        c=complete()
        c["live_stats"]["independently_verified"]=False
        self.assertIn("LIVE_STATS_NOT_INDEPENDENTLY_VERIFIED",
                      evaluate(c,now=NOW)["blockers"])

    def test_model_requires_true_forward_samples_not_synthetic(self):
        c=complete()
        c["model"]["independent_settled_forward_samples"]=0
        self.assertIn("INSUFFICIENT_INDEPENDENT_SETTLED_SAMPLES",
                      evaluate(c,now=NOW)["blockers"])
        c["model"]["independent_settled_forward_samples"]=True
        self.assertIn("INSUFFICIENT_INDEPENDENT_SETTLED_SAMPLES",
                      evaluate(c,now=NOW)["blockers"])

    def test_model_market_mismatch_blocks(self):
        c=complete()
        c["model"]["supported_market"]="h2h"
        self.assertIn("LEAGUE_OR_MARKET_NOT_CALIBRATED",
                      evaluate(c,now=NOW)["blockers"])

    def test_missing_out_of_sample_or_leakage_audit_blocks(self):
        for field in ("calibration_verified","leakage_audit_passed","out_of_sample_verified"):
            c=complete()
            c["model"][field]=False
            self.assertIn("MODEL_CALIBRATION_OR_LEAKAGE_UNVERIFIED",
                          evaluate(c,now=NOW)["blockers"])

    def test_clock_timezone_required(self):
        c=complete()
        c["screenshot"]["observed_at_utc"]="2026-10-09T13:59:30"
        self.assertFalse(evaluate(c,now=NOW)["gate_checks"]["screenshot_clock"])

    def test_future_source_clock_rejected(self):
        c=complete()
        c["market"]["last_update_utc"]="2026-10-09T14:02:00Z"
        self.assertFalse(evaluate(c,now=NOW)["gate_checks"]["market_clock"])

    def test_negative_goals_and_bool_minute_rejected(self):
        for field,value in (("home_goals",-1),("minute",True)):
            c=complete()
            c["screenshot"][field]=value
            self.assertIn("SCREENSHOT_SCORE_OR_MINUTE_UNVERIFIED",
                          evaluate(c,now=NOW)["blockers"])

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([],now=NOW)
        with self.assertRaises(ValueError):
            evaluate({},now=datetime(2026,10,9,14))

if __name__=="__main__":
    unittest.main()
