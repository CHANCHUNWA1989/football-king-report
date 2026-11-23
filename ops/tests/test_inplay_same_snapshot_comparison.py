"""Adversarial synthetic same-snapshot research comparison; no external data."""
import copy
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_same_snapshot_comparison import compare


def sample():
    case = {
        "fixture":{"fixture_id":"event_123","home_id":"river","away_id":"lanus",
                   "kickoff_utc":"2026-11-23T00:00:00Z"},
        "prematch":{"home_goals_per_90":1.5,"away_goals_per_90":1.1,
                    "generated_utc":"2026-11-22T23:30:00Z",
                    "origin":"UNATTESTED_RESEARCH_ASSUMPTION"},
        "state":{"fixture_id":"event_123","observed_utc":"2026-11-23T00:52:00Z",
                 "as_of_utc":"2026-11-23T00:52:10Z","match_status":"HALF_TIME",
                 "elapsed_regulation_minutes":45,"home_goals":1,"away_goals":1,
                 "home_red_cards":0,"away_red_cards":0}}
    snap = {
        "fixture_id":"event_123","kickoff_utc":"2026-11-23T00:00:00Z",
        "decision_utc":"2026-11-23T00:52:10Z","minute_elapsed":45,
        "score_home":1,"score_away":1,"red_home":0,"red_away":0,
        "prematch":{"fixture_id":"event_123","model_id":"unverified_study_model",
                    "forecast_utc":"2026-11-22T23:30:00+00:00",
                    "inputs_available_utc":"2026-11-22T23:29:00Z",
                    "expected_home_goals":1.5,"expected_away_goals":1.1,
                    "input_sha256":"a"*64,"production_recommendations":"DISABLED",
                    "calibrated":False},
        "event_consensus":{"status":"RESEARCH_ONLY","fixture_id":"event_123",
                           "decision_utc":"2026-11-23T00:52:10Z",
                           "score_home":1,"score_away":1,
                           "active_red_cards":{"HOME":0,"AWAY":0},
                           "production_recommendations":"DISABLED",
                           "model_scoring_eligible":False,
                           "source_authenticated":False,
                           "source_independence_verified":False,
                           "evidence_input_sha256":"b"*64}}
    out = {
        "schema":"football-king-vnext-inplay-comeback-challenger-v1",
        "status":"RESEARCH_ONLY","model_id":"inplay-fixed-score-state-v1-uncalibrated",
        "fixture_id":"event_123","decision_utc":"2026-11-23T00:52:10Z",
        "minute_elapsed":45,"current_score":[1,1],
        "input_evidence_sha256_unattested":"b"*64,
        "prematch_input_sha256_unattested":"a"*64,
        "remaining_expected_home_goals":.75,"remaining_expected_away_goals":.55,
        "fulltime_probabilities":{"HOME":.5,"DRAW":.2,"AWAY":.3},
        "trailing_team":None,"trailing_team_comeback_win_probability":None,
        "top_fulltime_scores":[],"fixed_coefficients_not_trained":True,
        "stoppage_time_not_modelled":True,
        "independent_clock_attestation":False,"source_authenticated":False,
        "model_calibrated":False,"model_scoring_eligible":False,
        "positive_ev_verified":False,"betting_recommendation_allowed":False,
        "production_recommendations":"DISABLED"}
    return case,snap,out


class SameSnapshotTests(unittest.TestCase):
    def test_matched_claim_is_still_never_formally_certified(self):
        c,s,o=sample()
        before=copy.deepcopy((c,s,o))
        r=compare(c,s,o)
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["certified_paired_samples"],0)
        self.assertFalse(r["prediction_execution_authenticated"])
        self.assertFalse(r["eligible_for_formal_comparison"])
        self.assertIsNone(r["recommendation"])
        self.assertIsNone(r["roi"])
        self.assertEqual(r["comparison"]["challenger_claimed_1x2"],
                         {"HOME":.5,"DRAW":.2,"AWAY":.3})
        self.assertAlmostEqual(sum(r["comparison"]["baseline_1x2"].values()),1,places=6)
        self.assertEqual(before,(c,s,o))

    def test_baseline_hold_can_never_be_overridden(self):
        for key,value in (("home_red_cards",1),("as_of_utc","2026-11-23T01:30:00Z")):
            c,s,o=sample()
            c["state"][key]=value
            self.assertTrue(compare(c,s,o)["reason"].startswith("BASELINE_HOLD:"))

    def test_fixture_and_clock_conflicts(self):
        for key,value in (("fixture_id","other"),
                          ("kickoff_utc","2026-11-23T00:01:00Z")):
            c,s,o=sample()
            s[key]=value
            self.assertEqual(compare(c,s,o)["reason"],"FIXTURE_OR_KICKOFF_MISMATCH")
        for key,value in (("decision_utc","2026-11-23T00:52:11Z"),
                          ("minute_elapsed",44),("score_home",2),
                          ("red_away",1),("minute_elapsed",True)):
            c,s,o=sample()
            s[key]=value
            self.assertEqual(compare(c,s,o)["reason"],"MATCH_STATE_OR_DECISION_MISMATCH")

    def test_prematch_must_be_same_frozen_input(self):
        for key,value in (("forecast_utc","2026-11-22T23:31:00Z"),
                          ("inputs_available_utc","2026-11-23T00:01:00Z"),
                          ("expected_home_goals",1.6),
                          ("expected_away_goals",1.2),
                          ("calibrated",True),
                          ("production_recommendations","ENABLED")):
            c,s,o=sample()
            s["prematch"][key]=value
            self.assertEqual(compare(c,s,o)["reason"],"PREMATCH_INPUT_NOT_SAME_SNAPSHOT")

    def test_source_receipt_conflicts(self):
        for key,value in (("score_home",2),("source_authenticated",True),
                          ("source_independence_verified",True),
                          ("active_red_cards",{"HOME":False,"AWAY":0})):
            c,s,o=sample()
            s["event_consensus"][key]=value
            self.assertEqual(compare(c,s,o)["reason"],
                             "UNTRUSTED_OR_MISMATCHED_EVENT_CONSENSUS")
        for key in ("final_score","odds","result","roi"):
            c,s,o=sample()
            s["event_consensus"][key]="2-2"
            self.assertEqual(compare(c,s,o)["reason"],
                             "POSTMATCH_OR_MARKET_DATA_IN_EVENT_PROOF")

    def test_claimed_challenger_probabilities_not_forgiven(self):
        for probs in ({"HOME":.4,"DRAW":.2,"AWAY":.3},
                      {"HOME":.5,"DRAW":.2,"AWAY":float("nan")},
                      {"HOME":True,"DRAW":.2,"AWAY":.3},
                      {"HOME":.5,"DRAW":.2},
                      {"HOME":.5,"DRAW":.2,"AWAY":.3,"CERTIFIED":0}):
            c,s,o=sample()
            o["fulltime_probabilities"]=probs
            self.assertEqual(compare(c,s,o)["status"],"HOLD")

    def test_fake_certification_and_extra_fields_rejected(self):
        for key,value in (("source_authenticated",True),
                          ("independent_clock_attestation",True),
                          ("positive_ev_verified",True),
                          ("model_calibrated",True),
                          ("production_recommendations","ENABLED")):
            c,s,o=sample()
            o[key]=value
            self.assertEqual(compare(c,s,o)["status"],"HOLD")
        c,s,o=sample()
        o["authenticated_quote"]=1.80
        self.assertEqual(compare(c,s,o)["reason"],"INVALID_CHALLENGER_OUTPUT_SCHEMA")

    def test_hash_and_claimed_challenger_state_required(self):
        c,s,o=sample()
        o["prematch_input_sha256_unattested"]="c"*64
        self.assertEqual(compare(c,s,o)["status"],"HOLD")
        for key,value in (("decision_utc","2026-11-23T00:52:15Z"),
                          ("minute_elapsed",46),("current_score",[1,2]),
                          ("current_score",[True,1])):
            c,s,o=sample()
            o[key]=value
            self.assertEqual(compare(c,s,o)["status"],"HOLD")

    def test_comeback_claim_must_match_1x2(self):
        c,s,o=sample()
        c["state"]["home_goals"]=0
        s["score_home"]=0
        s["event_consensus"]["score_home"]=0
        o["current_score"]=[0,1]
        o["trailing_team"]="HOME"
        o["trailing_team_comeback_win_probability"]=.5
        self.assertEqual(compare(c,s,o)["status"],"RESEARCH_ONLY")
        o["trailing_team_comeback_win_probability"]=.8
        self.assertEqual(compare(c,s,o)["reason"],"CONTRADICTORY_COMEBACK_PROBABILITY")

    def test_utc_instant_equivalence_and_no_postmatch_inputs(self):
        c,s,o=sample()
        s["decision_utc"]="2026-11-23T08:52:10+08:00"
        s["prematch"]["forecast_utc"]="2026-11-23T07:30:00+08:00"
        self.assertEqual(compare(c,s,o)["status"],"RESEARCH_ONLY")
        s["final_score"]=[3,1]
        self.assertEqual(compare(c,s,o)["reason"],"INVALID_CHALLENGER_SNAPSHOT_SCHEMA")
        c,s,o=sample()
        s["prematch"]["certified"]=True
        self.assertEqual(compare(c,s,o)["reason"],"INVALID_CHALLENGER_PREMATCH_SCHEMA")


if __name__ == "__main__":
    unittest.main()
