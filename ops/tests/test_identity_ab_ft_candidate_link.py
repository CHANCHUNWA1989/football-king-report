"""Synthetic outcomes ONLY; true sealed probability files are read untouched."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import unittest

from ops import identity_ab_ft_candidate_link as match
from ops import identity_ab_sealed_archive_audit as archive

ROOT=(Path(__file__).resolve().parents[2]
      /"evidence/identity_ab_forward/v1/42444100017-1")


def sealed():
    data=archive._read(ROOT,"83231.json",archive.MAX_RECORD_BYTES)
    return archive._parse(data,expected=archive.RECORD_KEYS)


def observation(record=None, *, finished=True, score=None):
    rec=record or sealed()
    return {
        "matchID":int(rec["provider_native_event_id"]),
        "leagueShortcut":"bl1",
        "leagueSeason":2026,
        "leagueId":4331,
        "team1":{"teamId":175,"teamName":rec["home"]},
        "team2":{"teamId":200,"teamName":rec["away"]},
        "matchDateTimeUTC":rec["scheduled_kickoff_utc"],
        "matchIsFinished":finished,
        "matchResults":(
            [{"resultTypeKind":"After90Minutes",
              "pointsTeam1":2,"pointsTeam2":1}]
            if score is None and finished else (score if score is not None else [])),
    }


def clock(*, after=4):
    return (datetime.fromisoformat(sealed()["scheduled_kickoff_utc"])
            +timedelta(hours=after)).isoformat()


def eval_source(rows, *, now=None):
    return match.link(ROOT,json.dumps(rows,sort_keys=True).encode("utf-8"),
                      observed_utc=now or clock(),transport_verified=False)


class OneSourceResultCandidateTests(unittest.TestCase):
    def test_prematch_all_nineteen_remain_pending_and_unscored(self):
        before=(datetime.fromisoformat(
            archive.EXPECTED_RECEIVED_UTC)+timedelta(minutes=5)).isoformat()
        result=eval_source([observation(finished=False)],now=before)
        self.assertEqual(result["sealed_forward_forecast_count"],19)
        self.assertEqual(sum(result["case_state_counts"].values()),19)
        self.assertEqual(result["case_state_counts"]["PREMATCH_PENDING"],19)
        self.assertEqual(result["one_source_90m_score_candidate_count"],0)
        self.assertEqual(result["certified_scored_case_count"],0)
        self.assertFalse(result["model_accuracy_uplift_proven"])

    def test_single_source_exact_id_club_kickoff_and_90min_finds_candidate_not_certified(self):
        source=observation()
        original=(ROOT/"83231.json").read_bytes()
        result=eval_source([source])
        self.assertEqual(sum(result["case_state_counts"].values()),19)
        self.assertEqual(result["one_source_90m_score_candidate_count"],1)
        self.assertEqual(result["matched_native_id_count"],1)
        row=next(x for x in result["case_states"]
                 if x["provider_native_event_id"]=="83231")
        self.assertEqual(row["result_state"],"SINGLE_SOURCE_90M_SCORE_CANDIDATE")
        self.assertEqual(row["single_source_score_candidate"],[2,1])
        self.assertFalse(row["actual_kickoff_authenticated"])
        self.assertFalse(row["model_scoring_eligible"])
        self.assertFalse(row["regulation_ft_independently_authenticated"])
        self.assertEqual(result["independently_verified_ft_count"],0)
        self.assertEqual(result["certified_scored_case_count"],0)
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertEqual((ROOT/"83231.json").read_bytes(),original)

    def test_provider_native_id_must_not_fuzzy_join_teams(self):
        source=observation()
        source["matchID"]=99991
        report=eval_source([source])
        self.assertEqual(report["matched_native_id_count"],0)
        self.assertEqual(report["one_source_90m_score_candidate_count"],0)
        target=next(row for row in report["case_states"]
                    if row["provider_native_event_id"]=="83231")
        self.assertEqual(target["result_state"],"NATIVE_RESULT_NOT_FOUND")
        self.assertIsNone(target["single_source_score_candidate"])
        self.assertEqual(sum(report["case_state_counts"].values()),19)

    def test_wrong_home_club_or_away_club_blocks_score_even_if_native_id_matches(self):
        for side,name in (("team1","FC Schalke 04"),
                          ("team2","FC Bayern München")):
            source=observation()
            source[side]["teamName"]=name
            with self.subTest(side=side):
                result=eval_source([source])
                case=next(x for x in result["case_states"]
                          if x["provider_native_event_id"]=="83231")
                self.assertEqual(case["result_state"],
                                 "NATIVE_ID_OR_CLUB_IDENTITY_CONFLICT_HOLD")
                self.assertIsNone(case["single_source_score_candidate"])

    def test_schedule_change_does_not_falsely_authorize_ft(self):
        source=observation()
        source["matchDateTimeUTC"]=(
            datetime.fromisoformat(source["matchDateTimeUTC"])
            +timedelta(hours=2)).isoformat()
        result=eval_source([source])
        self.assertEqual(result["case_state_counts"]["SCHEDULED_KICKOFF_CHANGED_HOLD"],1)
        self.assertEqual(result["one_source_90m_score_candidate_count"],0)

    def test_observation_before_kickoff_cannot_contain_authorized_ft(self):
        before=(datetime.fromisoformat(sealed()["scheduled_kickoff_utc"])
                -timedelta(hours=1)).isoformat()
        result=eval_source([observation()],now=before)
        self.assertEqual(
            result["case_state_counts"]["SOURCE_FT_BEFORE_SEALED_KICKOFF_HOLD"],1)
        self.assertEqual(result["one_source_90m_score_candidate_count"],0)

    def test_provider_claimed_finished_within_three_hours_still_held(self):
        result=eval_source([observation()],now=clock(after=2))
        self.assertEqual(
            result["case_state_counts"]["CANDIDATE_TOO_EARLY_AFTER_SCHEDULED_KICKOFF_HOLD"],1)
        self.assertEqual(result["one_source_90m_score_candidate_count"],0)

    def test_provisional_match_is_never_90min_final(self):
        result=eval_source([observation(finished=False,
                                         score=[{"resultTypeKind":"HalfTime",
                                                 "pointsTeam1":1,"pointsTeam2":0}])])
        self.assertEqual(result["case_state_counts"]["NOT_REPORTED_FINISHED"],1)
        self.assertEqual(result["one_source_90m_score_candidate_count"],0)

    def test_half_time_only_duplicate_90min_or_invalid_score_blocked(self):
        invalids=[
            [{"resultTypeKind":"HalfTime","pointsTeam1":2,"pointsTeam2":1}],
            [{"resultTypeKind":"After90Minutes","pointsTeam1":2,"pointsTeam2":1},
             {"resultTypeKind":"After90Minutes","pointsTeam1":2,"pointsTeam2":1}],
            [{"resultTypeKind":"After90Minutes","pointsTeam1":2,"pointsTeam2":True}],
            [{"resultTypeKind":"After90Minutes","pointsTeam1":-1,"pointsTeam2":0}],
            None,
        ]
        for value in invalids:
            source=observation(score=value if value is not None else [])
            with self.subTest(value=value):
                report=eval_source([source])
                self.assertEqual(report["case_state_counts"][
                    "MISSING_OR_AMBIGUOUS_90M_RESULT_HOLD"],1)
                self.assertEqual(report["one_source_90m_score_candidate_count"],0)

    def test_duplicate_provider_native_id_fails_closed(self):
        source=observation()
        with self.assertRaisesRegex(match.CandidateLinkError,
                                    "DUPLICATE_NATIVE_RESULT_MATCH"):
            eval_source([source,copy.deepcopy(source)])

    def test_duplicate_json_key_and_nonfinite_payload_fails_closed(self):
        for raw in (b'[{"matchID":83231,"matchID":83231}]',b'[NaN]'):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(match.CandidateLinkError,
                                            "INVALID_RESULT_SOURCE_JSON"):
                    match.link(ROOT,raw,observed_utc=clock())

    def test_changed_archived_forecast_is_rejected_before_result_matching(self):
        # Reading the *true* 19 files must precede outcome observations.
        with unittest.mock.patch.object(archive,"PINNED_INDEX_GIT_BLOB_SHA1",
                                        "0"*40):
            # The audit uses the same module globals as the patch.
            with self.assertRaises(archive.ForwardArchiveAuditError):
                eval_source([observation()])

    def test_invalid_archive_path_does_not_accept_source(self):
        with self.assertRaises(archive.ForwardArchiveAuditError):
            match.link(ROOT.parent, b"[]",observed_utc=clock())

    def test_all_nineteen_denominator_retained_on_empty_provider_snapshot(self):
        result=eval_source([])
        self.assertEqual(len(result["case_states"]),19)
        self.assertEqual(sum(result["case_state_counts"].values()),19)
        self.assertEqual(result["one_source_90m_score_candidate_count"],0)
        self.assertEqual(result["certified_scored_case_count"],0)


if __name__=="__main__":
    unittest.main()
