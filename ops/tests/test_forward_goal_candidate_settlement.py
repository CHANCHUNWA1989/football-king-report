import copy
from datetime import datetime, timedelta, timezone
import unittest

from ops.forward_goal_shadow_cohort_seal import build
from ops.forward_goal_candidate_settlement import audit

SOURCE_NOW = datetime(2026, 11, 16, 15, 30, tzinfo=timezone.utc)
AFTER = datetime(2026, 11, 23, 15, 30, tzinfo=timezone.utc)
REV = "e466196956a0780776bc90ef1168f6c462024c3e"


def fixture(mid, kickoff):
    return {"fixture_id": f"openligadb:{mid}",
            "home_team_id": str(mid*2), "away_team_id": str(mid*2+1),
            "kickoff_utc": kickoff}


def make_snapshot(missing_second=False):
    payload = {
        "schema":"football-king-forward-goal-shadow-cohort-v1",
        "production_recommendations":"DISABLED",
        "source":{
            "namespace":"openligadb", "league":"bundesliga",
            "source_response_sha256":"a"*64,
            "source_received_utc":"2026-11-16T15:20:00Z",
            "source_capture_id":"github-actions:43898363049:1",
        },
        "training":{
            "league":"bundesliga", "training_source_sha256":"a"*64,
            "training_cutoff_utc":"2026-11-08T18:30:00Z",
            "training_match_count":81,
            "over25_frequency":0.70, "btts_frequency":0.60,
        },
        "fixtures":[
            fixture(83237,"2026-11-20T19:30:00Z"),
            fixture(83238,"2026-11-21T14:30:00Z")
        ],
        "forecasts":[{
            "fixture_id":"openligadb:83237", "model_revision_sha":REV,
            "computed_utc":"2026-11-16T15:25:00Z",
            "expected_home_goals":1.8, "expected_away_goals":1.1,
        }],
    }
    if not missing_second:
        payload["forecasts"].append({
            "fixture_id":"openligadb:83238", "model_revision_sha":REV,
            "computed_utc":"2026-11-16T15:25:00Z",
            "expected_home_goals":1.3, "expected_away_goals":1.2,
        })
    return build(payload,now=SOURCE_NOW)


def obs(provider, fixture="openligadb:83237", score=(2, 1), hash_letter="b",
        captured="2026-11-20T21:10:00Z"):
    return {"fixture_id":fixture,"provider_namespace":provider,
            "provider_fixture_id":f"{provider}-native-1",
            "captured_utc":captured,"raw_response_sha256":hash_letter*64,
            "status":"FT","home_goals":score[0],"away_goals":score[1]}


def evaluate(snapshot, observations=None, **kwargs):
    return audit(
        snapshot, observations if observations is not None else [],
        expected_snapshot_sha256=kwargs.get("expected_snapshot_sha256",snapshot["sha256"]),
        expected_capture_id=kwargs.get("expected_capture_id","github-actions:43898363049:1"),
        now=kwargs.get("now",AFTER),
    )


class ForwardGoalCandidateSettlementTests(unittest.TestCase):
    def test_no_results_returns_all_pending_without_winner_selection(self):
        snapshot=make_snapshot()
        r=evaluate(snapshot)
        self.assertEqual(r["entire_original_cohort_retained"],2)
        self.assertEqual(r["unmatched_or_unscored_cases_retained"],2)
        self.assertEqual(r["paired_market_diagnostics"]["over25"]["candidate_scored"],0)
        self.assertIsNone(r["paired_market_diagnostics"]["btts"]["blend_brier"])
        self.assertEqual(r["candidate_provider_agreements_only"],0)
        self.assertFalse(r["eligible_for_model_promotion"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["production_recommendations"],"DISABLED")

    def test_two_agreed_sources_score_only_matching_fixture_not_all(self):
        snap=make_snapshot()
        r=evaluate(snap,[obs("provider-one"),obs("provider-two",hash_letter="c")])
        self.assertEqual(r["entire_original_cohort_retained"],2)
        self.assertEqual(r["candidate_provider_agreements_only"],1)
        self.assertEqual(r["paired_market_diagnostics"]["over25"]["candidate_scored"],1)
        self.assertEqual(r["paired_market_diagnostics"]["btts"]["observed_positive_rate"],1.0)
        self.assertEqual(r["fixtures"][0]["candidate_score_ft"],[2,1])
        self.assertEqual(r["fixtures"][1]["settlement_state"],"WAITING_TWO_SOURCES")
        self.assertEqual(r["certified_independent_forward_cases"],0)
        self.assertFalse(r["official_final_result_independently_verified"])

    def test_any_disagreement_for_one_fixture_holds_and_never_cherrypicks(self):
        snap=make_snapshot()
        observations=[
            obs("provider-one"),
            obs("provider-two",hash_letter="c"),
            obs("provider-three",score=(1,1),hash_letter="d"),
        ]
        r=evaluate(snap,observations)
        self.assertEqual(r["candidate_provider_agreements_only"],0)
        self.assertEqual(r["fixture_states"]["CONFLICTING_FINAL_SCORES_HOLD"],1)
        self.assertEqual(r["paired_market_diagnostics"]["over25"]["candidate_scored"],0)

    def test_same_raw_provider_bytes_not_independent_candidate(self):
        snap=make_snapshot()
        r=evaluate(snap,[obs("provider-one"),obs("provider-two",hash_letter="b")])
        self.assertEqual(r["fixtures"][0]["settlement_state"],"SAME_RAW_EVIDENCE_HOLD")
        self.assertEqual(r["candidate_provider_agreements_only"],0)

    def test_single_provider_cannot_certify_result(self):
        r=evaluate(make_snapshot(),[obs("provider-one")])
        self.assertEqual(r["fixtures"][0]["settlement_state"],"WAITING_SECOND_PROVIDER")
        self.assertEqual(r["paired_market_diagnostics"]["over25"]["candidate_scored"],0)

    def test_future_fixture_must_remain_pending(self):
        r=evaluate(make_snapshot(),now=SOURCE_NOW+timedelta(hours=1))
        self.assertEqual(r["fixture_states"],{"MATCH_NOT_MATURED":2})

    def test_duplicate_provider_is_rejected_even_when_scores_agree(self):
        a=obs("provider-one")
        with self.assertRaisesRegex(ValueError,"DUPLICATE_RESULT_PROVIDER"):
            evaluate(make_snapshot(),[a,dict(a)])

    def test_unlisted_fixtures_must_not_enter_selected_metrics(self):
        with self.assertRaisesRegex(ValueError,"RESULT_FOR_UNLISTED_FIXTURE"):
            evaluate(make_snapshot(),[obs("provider-one",fixture="openligadb:83299")])

    def test_before_90min_or_future_result_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"RESULT_TIME_PREMATURE"):
            evaluate(make_snapshot(),[obs("provider-one",captured="2026-11-20T20:00:00Z")])
        with self.assertRaisesRegex(ValueError,"RESULT_TIME_PREMATURE"):
            evaluate(make_snapshot(),[obs("provider-one",captured="2026-11-24T00:00:00Z")])

    def test_pin_snapshot_and_capture_id_against_artifact(self):
        snap=make_snapshot()
        with self.assertRaisesRegex(ValueError,"PINNED_SNAPSHOT_HASH_MISMATCH"):
            evaluate(snap,expected_snapshot_sha256="f"*64)
        with self.assertRaisesRegex(ValueError,"CAPTURE_RUN_ID_MISMATCH"):
            evaluate(snap,expected_capture_id="github-actions:other:1")
        bad=copy.deepcopy(snap)
        bad["payload"]["fixtures"][0]["fixture"]["away_team_id"]="rogue-team"
        with self.assertRaisesRegex(ValueError,"COHORT_ENVELOPE_TAMPERED"):
            evaluate(bad)

    def test_invalid_score_metadata_and_extra_market_quote_fails_closed(self):
        p=obs("provider-one")
        p["home_goals"]=True
        with self.assertRaisesRegex(ValueError,"INVALID_FINAL_SCORE"):
            evaluate(make_snapshot(),[p])
        p=obs("provider-one")
        p["status"]="HT"
        with self.assertRaisesRegex(ValueError,"RESULT_NOT_90_MINUTE_FINAL"):
            evaluate(make_snapshot(),[p])
        p=obs("provider-one")
        p["odds"]=2.05
        with self.assertRaisesRegex(ValueError,"INVALID_RESULT_OBSERVATION_CONTRACT"):
            evaluate(make_snapshot(),[p])

    def test_no_original_prediction_stays_unscored_even_with_agreement(self):
        r=evaluate(make_snapshot(missing_second=True),[
            obs("provider-one",fixture="openligadb:83238",hash_letter="b",
                captured="2026-11-21T16:10:00Z"),
            obs("provider-two",fixture="openligadb:83238",hash_letter="c",
                captured="2026-11-21T16:10:00Z"),
        ])
        self.assertEqual(r["candidate_provider_agreements_only"],1)
        self.assertEqual(r["paired_market_diagnostics"]["over25"]["candidate_scored"],0)
        missing=next(x for x in r["fixtures"] if x["fixture_id"]=="openligadb:83238")
        self.assertEqual(missing["forecast_state"],"HOLD_NO_PREMATCH_MODEL")
        self.assertEqual(missing["markets"],{})

    def test_training_only_prior_is_scored_on_exact_same_fixture(self):
        s=make_snapshot()
        r=evaluate(s,[obs("one"),obs("two",hash_letter="c")])
        m=r["paired_market_diagnostics"]["over25"]
        self.assertEqual(m["candidate_scored"],1)
        expected_prior=s["payload"]["fixtures"][0]["over25"]["training_only_prior"]
        self.assertAlmostEqual(m["training_only_prior_brier"],(1-expected_prior)**2,places=8)
        self.assertIsNotNone(m["training_only_prior_logloss"])
        self.assertEqual(r["fixtures"][0]["markets"]["over25"]["training_only_prior_brier_contribution"],
                         round((1-expected_prior)**2,10))
        self.assertFalse(r["full_nine_fixture_cohort_scored"])
        self.assertIsNone(r["full_cohort_market_metrics_unverified"])
        self.assertTrue(r["paired_market_diagnostics_are_partial_unless_full_cohort"])

    def test_reused_native_event_for_two_fixtures_must_hold(self):
        first=obs("one",fixture="openligadb:83237")
        second=obs("one",fixture="openligadb:83238",
                   captured="2026-11-21T16:10:00Z")
        # Existing helper assigns one fixed provider-native ID across both.
        with self.assertRaisesRegex(ValueError,"PROVIDER_NATIVE_EVENT_REUSED_ACROSS_FIXTURES"):
            evaluate(make_snapshot(),[first,second])

    def test_complete_nine_case_research_scores_all_three_comparators(self):
        original=make_snapshot()
        envelope=original["payload"]
        payload={
            "schema":"football-king-forward-goal-shadow-cohort-v1",
            "production_recommendations":"DISABLED",
            "source":copy.deepcopy(envelope["source"]),
            "training":copy.deepcopy(envelope["training"]),
            "fixtures":[copy.deepcopy(x["fixture"]) for x in envelope["fixtures"]],
            "forecasts":[],
        }
        for x in envelope["fixtures"]:
            if x["state"]=="UNVERIFIED_PREMATCH_RESEARCH_FORECAST":
                payload["forecasts"].append({
                    "fixture_id":x["fixture"]["fixture_id"],
                    "model_revision_sha":REV,
                    "computed_utc":"2026-11-16T15:25:00Z",
                    "expected_home_goals":x["original_a_rates"]["home"],
                    "expected_away_goals":x["original_a_rates"]["away"],
                })
        for i in range(83239,83246):
            fid=f"openligadb:{i}"
            payload["fixtures"].append(fixture(i,"2026-11-22T14:30:00Z"))
            payload["forecasts"].append({
                "fixture_id":fid,"model_revision_sha":REV,
                "computed_utc":"2026-11-16T15:25:00Z",
                "expected_home_goals":1.4,"expected_away_goals":1.1,
            })
        frozen=build(payload,now=SOURCE_NOW)
        o=[]
        for x in payload["fixtures"]:
            fid=x["fixture_id"]
            kickoff=datetime.fromisoformat(x["kickoff_utc"].replace("Z","+00:00"))
            cap=(kickoff+timedelta(hours=2)).isoformat()
            for p,ch in (("one","b"),("two","c")):
                item=obs(p,fixture=fid,hash_letter=ch,captured=cap)
                item["provider_fixture_id"]=p+"-"+fid
                o.append(item)
        full=evaluate(frozen,o)
        self.assertEqual(full["entire_original_cohort_retained"],9)
        self.assertEqual(full["paired_market_diagnostics"]["over25"]["candidate_scored"],9)
        self.assertTrue(full["full_nine_fixture_cohort_scored"])
        self.assertFalse(full["paired_market_diagnostics_are_partial_unless_full_cohort"])
        self.assertIsNotNone(full["full_cohort_market_metrics_unverified"])
        self.assertEqual(full["full_cohort_market_metrics_unverified"]["over25"]["candidate_scored"],9)
        self.assertIsNotNone(full["full_cohort_market_metrics_unverified"]["btts"]["training_only_prior_brier"])
        self.assertFalse(full["full_cohort_independently_certified"])
        self.assertEqual(full["production_recommendations"],"DISABLED")

    def test_readonly_does_not_mutate_forecast_or_source_observations(self):
        snap=make_snapshot()
        observes=[obs("provider-one"),obs("provider-two",hash_letter="c")]
        before=copy.deepcopy((snap,observes))
        evaluate(snap,observes)
        self.assertEqual((snap,observes),before)


if __name__ == "__main__":
    unittest.main()
