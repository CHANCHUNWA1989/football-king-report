"""All-synthetic score claims compared with REAL 19 pinned pre-match files."""
import copy
from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest

from ops import identity_ab_two_provider_result_review as dual
from ops.tests.test_identity_ab_ft_candidate_link import (
    ROOT, sealed, observation, clock,
)


def second(*, score=(2,1), with_time=True, wrong_day=False,
           home=None, away=None):
    rec=sealed()
    ko=datetime.fromisoformat(rec["scheduled_kickoff_utc"])
    local=ko.astimezone(dual.BERLIN)
    match={
        "round":"Matchday 9",
        "date": (local.date()+timedelta(days=1)).isoformat() if wrong_day
                else local.date().isoformat(),
        "team1":home or rec["home"],
        "team2":away or rec["away"],
    }
    if with_time:
        match["time"]=local.strftime("%H:%M")
    if score is not None:
        match["score"]={"ft":list(score)}
    return match


def encoded(matches, *, title=dual.SEASON_TITLE):
    return json.dumps({"name":title,"matches":matches},
                      separators=(",",":")).encode("utf-8")


def evaluate(first=None, second_matches=None, *, now=None):
    first=[] if first is None else first
    second_matches=[] if second_matches is None else second_matches
    return dual.compare(ROOT,json.dumps(first).encode(),
                        encoded(second_matches),
                        observed_utc=now or clock(after=4),
                        transport_verified=True)


def row(report):
    return next(x for x in report["per_fixture"]
                if x["provider_native_event_id"]=="83231")


class TwoProviderForwardCohortTests(unittest.TestCase):
    def test_all_19_still_pending_and_not_scored_before_first_kickoff(self):
        now=(datetime.fromisoformat(sealed()["source_response_received_utc"])
             +timedelta(minutes=8)).isoformat()
        result=evaluate([observation(finished=False)],[second(score=None)],now=now)
        self.assertEqual(result["original_forecast_count"],19)
        self.assertEqual(len(result["per_fixture"]),19)
        self.assertEqual(result["case_state_counts"]["PREMATCH_PENDING"],19)
        self.assertEqual(result["certified_scored_cases"],0)
        self.assertFalse(result["model_accuracy_improved_proven"])
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_exact_two_score_claims_agree_but_not_certified(self):
        result=evaluate([observation()],[second()])
        self.assertEqual(len(result["per_fixture"]),19)
        self.assertEqual(sum(result["case_state_counts"].values()),19)
        self.assertEqual(result["two_provider_matching_score_candidates"],1)
        case=row(result)
        self.assertEqual(case["comparison_state"],
                         "TWO_PROVIDER_90M_SCORE_AGREEMENT_CANDIDATE")
        self.assertEqual(case["first_source_90m_score"],[2,1])
        self.assertEqual(case["second_source_explicit_ft_score"],[2,1])
        self.assertFalse(case["publisher_upstream_independence_authenticated"])
        self.assertFalse(case["model_scoring_eligible"])
        self.assertEqual(result["independently_verified_regulation_ft"],0)
        self.assertEqual(result["certified_scored_cases"],0)

    def test_conflicting_90_minute_scores_block_without_majority_vote(self):
        result=evaluate([observation()],[second(score=(3,1))])
        self.assertEqual(result["two_provider_matching_score_candidates"],0)
        self.assertEqual(result["two_provider_conflicting_score_candidates"],1)
        self.assertEqual(row(result)["comparison_state"],
                         "TWO_PROVIDER_90M_SCORE_CONFLICT")
        self.assertFalse(row(result)["model_scoring_eligible"])

    def test_wrong_team_cannot_match_even_if_score_and_date_agree(self):
        result=evaluate([observation()],[second(home="FC Bayern München")])
        self.assertEqual(row(result)["comparison_state"],
                         "SECOND_SOURCE_MISSING")
        self.assertEqual(result["two_provider_matching_score_candidates"],0)

    def test_wrong_local_berlin_date_cannot_match(self):
        result=evaluate([observation()],[second(wrong_day=True)])
        self.assertEqual(row(result)["comparison_state"],"SECOND_SOURCE_MISSING")

    def test_wrong_second_source_time_is_not_silently_accepted(self):
        wrong=second()
        wrong["time"]="00:01"
        result=evaluate([observation()],[wrong])
        self.assertEqual(row(result)["comparison_state"],
                         "SECOND_SOURCE_SCHEDULE_TIME_CONFLICT")
        self.assertEqual(result["two_provider_matching_score_candidates"],0)

    def test_date_only_source_can_agree_but_never_prove_actual_kickoff(self):
        result=evaluate([observation()],[second(with_time=False)])
        self.assertEqual(result["two_provider_matching_score_candidates"],1)
        self.assertFalse(row(result)["actual_kickoff_authenticated"])
        self.assertEqual(result["certified_scored_cases"],0)

    def test_duplicate_second_source_fixture_rejected_as_ambiguous(self):
        fixture=second()
        report=evaluate([observation()],[fixture,copy.deepcopy(fixture)])
        self.assertEqual(row(report)["comparison_state"],
                         "SECOND_SOURCE_AMBIGUOUS_MATCH")
        self.assertEqual(report["two_provider_matching_score_candidates"],0)

    def test_no_explicit_ft_or_placeholder_score_not_a_result(self):
        for match in (second(score=None),{**second(),"score":[0,0]},
                      {**second(),"score":{"ht":[2,1]}},
                      {**second(),"score":{"ft":[2,True]}}):
            with self.subTest(match=match):
                report=evaluate([observation()],[match])
                self.assertEqual(row(report)["comparison_state"],
                                 "SECOND_SOURCE_NO_EXPLICIT_FT")
                self.assertEqual(report["two_provider_matching_score_candidates"],0)

    def test_first_source_not_finished_cannot_be_rescued_by_second(self):
        report=evaluate([observation(finished=False)],[second()])
        self.assertEqual(row(report)["comparison_state"],"FIRST_SOURCE_NOT_ELIGIBLE")
        self.assertEqual(report["two_provider_matching_score_candidates"],0)

    def test_first_source_kickoff_conflict_blocks_second_confirmation(self):
        bad=observation()
        changed=datetime.fromisoformat(bad["matchDateTimeUTC"])+timedelta(hours=2)
        bad["matchDateTimeUTC"]=changed.isoformat()
        report=evaluate([bad],[second()])
        self.assertEqual(row(report)["comparison_state"],"FIRST_SOURCE_NOT_ELIGIBLE")
        self.assertEqual(report["certified_scored_cases"],0)

    def test_duplicate_json_field_and_nan_rejected(self):
        for raw in (
            b'{"name":"Deutsche Bundesliga 2026/27","matches":[],"matches":[]}',
            b'{"name":"Deutsche Bundesliga 2026/27","matches":[NaN]}',
        ):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(dual.TwoProviderError,
                                            "INVALID_SECOND_PROVIDER_JSON"):
                    dual.compare(ROOT,b"[]",raw,observed_utc=clock(after=4))

    def test_wrong_season_rejected_before_publishing_results(self):
        with self.assertRaisesRegex(dual.TwoProviderError,
                                    "INVALID_SECOND_PROVIDER_LEAGUE_SEASON"):
            dual.compare(ROOT,b"[]",encoded([],title="German Bundesliga 2025/26"),
                         observed_utc=clock(after=4))

    def test_invalid_calendar_date_rejected(self):
        match=second()
        match["date"]="2026-99-88"
        with self.assertRaisesRegex(dual.TwoProviderError,
                                    "INVALID_SECOND_PROVIDER_LOCAL_DATE"):
            evaluate([observation()],[match])

    def test_no_matches_does_not_drop_old_predictions(self):
        report=evaluate([],[])
        self.assertEqual(len(report["per_fixture"]),19)
        self.assertEqual(sum(report["case_state_counts"].values()),19)
        self.assertEqual(report["two_provider_matching_score_candidates"],0)
        self.assertEqual(report["certified_scored_cases"],0)


if __name__=="__main__":
    unittest.main()
