"""Synthetic no-network tests for research-only same-fetch forward observation."""
import copy
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opponent_forward_capture import capture, MIN_LEAD_SECONDS, SCHEMA

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)
HK = ZoneInfo("Asia/Hong_Kong")
TEAMS = ("A", "B", "C", "D", "E", "F")


def past():
    history = []
    for i in range(72):
        day = (NOW - timedelta(days=i+1)).astimezone(HK).date().isoformat()
        history.append({
            "date": day, "home": TEAMS[i % 6], "away": TEAMS[(i + 1) % 6],
            "event_id": f"synthetic:history:{i}",
            "status": "FINISHED", "score_ft": [1 + int(i%3 == 0), int(i%4 == 0)],
            "kickoff_utc": None,
        })
    return history


def future(*, home="A", away="B", event="synthetic:scheduled:01"):
    kickoff = NOW + timedelta(days=2)
    return {
        "date": kickoff.astimezone(HK).date().isoformat(),
        "home": home, "away": away, "event_id": event,
        "status": "SCHEDULED", "score_ft": None,
        "kickoff_utc": kickoff.isoformat(),
    }


def mock_source(rows=None, captured=None, status="READY_RESEARCH"):
    return {
        "status": status,
        "source": "SyntheticPublicProvider",
        "captured_utc": (captured or NOW + timedelta(seconds=30)).isoformat(),
        "matches": past() + [future()] if rows is None else rows,
    }


class Times:
    def __init__(self, *times):
        self.times = list(times)
        self.index = 0

    def __call__(self):
        idx = min(self.index, len(self.times)-1)
        self.index += 1
        return self.times[idx]


def run(data=None, times=None, league="epl"):
    times = times or (
        NOW, NOW+timedelta(seconds=60), NOW+timedelta(seconds=100))
    payload = mock_source() if data is None else data
    return capture(
        league,
        lambda *, season, league, clock: payload,
        clock=Times(*times),
        commit_sha="a"*40,
    )


class SameFetchObservationTests(unittest.TestCase):
    def test_one_safe_pair_contains_old_A_and_new_without_results(self):
        r = run()
        self.assertEqual(r["schema"], SCHEMA)
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual(r["candidate_count"], 1)
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertEqual(r["run_entered_utc"], NOW.isoformat())
        self.assertEqual(r["snapshot_model_asof_utc"],
                         (NOW+timedelta(seconds=60)).isoformat())
        self.assertEqual(r["computation_completed_utc"],
                         (NOW+timedelta(seconds=100)).isoformat())
        row = r["candidates"][0]
        self.assertEqual(row["source_event_id_unverified"], future()["event_id"])
        self.assertFalse(row["result_or_settlement_included"])
        self.assertEqual(row["production_recommendations"], "DISABLED")
        self.assertEqual(row["original_training_sha256"].__len__(), 64)
        self.assertEqual(row["source_normalized_rows_sha256_not_raw_capture_proof"].__len__(), 64)
        for name in ("original_A", "opponent_strength_candidate"):
            probs = [row[name][k] for k in ("p_home", "p_draw", "p_away")]
            self.assertAlmostEqual(sum(probs), 1, places=6)
        for flag in (
            "source_capture_authenticated",
            "normalized_source_rows_cryptographically_attested",
            "model_clock_externally_attested",
            "historical_results_independently_verified",
            "eligible_for_formal_forward_scoring",
            "model_accuracy_improved",
            "positive_ev_verified",
            "market_quotes_queried",
        ):
            self.assertFalse(r[flag], flag)

    def test_same_snapshot_same_clock_produces_same_derived_candidate(self):
        a, b = run(), run()
        self.assertEqual(a, b)

    def test_missing_source_clock_is_hold(self):
        data = mock_source()
        del data["captured_utc"]
        self.assertEqual(run(data)["reason"], "SOURCE_CAPTURE_TIME_UNKNOWN")

    def test_source_claim_newer_than_model_clock_is_hold(self):
        data = mock_source(captured=NOW + timedelta(seconds=200))
        self.assertEqual(run(data)["reason"],
                         "SOURCE_CAPTURE_STALE_OR_CLOCK_CONFLICT")

    def test_stale_capture_is_hold(self):
        data = mock_source(captured=NOW - timedelta(seconds=901))
        self.assertEqual(run(data)["reason"],
                         "SOURCE_CAPTURE_STALE_OR_CLOCK_CONFLICT")

    def test_clock_reversal_is_hold(self):
        times = (
            NOW+timedelta(seconds=120), NOW+timedelta(seconds=60),
            NOW+timedelta(seconds=180))
        self.assertEqual(run(times=times)["status"], "HOLD")

    def test_clock_too_slow_is_hold(self):
        times = (
            NOW, NOW+timedelta(seconds=60), NOW+timedelta(seconds=300))
        self.assertEqual(run(times=times)["reason"],
                         "COMPUTE_CLOCK_CROSSED_BOUNDARY")

    def test_no_forecast_if_hong_kong_date_rolls_over(self):
        first = datetime(2026, 11, 21, 15, 59, 20, tzinfo=timezone.utc)
        data = mock_source(captured=first + timedelta(seconds=1))
        times = (first, first+timedelta(seconds=10), first+timedelta(seconds=50))
        self.assertEqual(run(data, times=times)["reason"],
                         "COMPUTE_CLOCK_CROSSED_BOUNDARY")

    def test_future_result_must_not_be_included(self):
        data = mock_source(rows=past() + [{**future(), "score_ft": [2, 0]}])
        r = run(data)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["candidate_count"], 0)

    def test_conflicting_event_identifiers_are_not_paired(self):
        data = mock_source(rows=past()+[future(), future(away="C")])
        r = run(data)
        self.assertEqual(r["status"], "HOLD")

    def test_disabled_source_status_blocks_pair(self):
        self.assertEqual(run(mock_source(status="HOLD"))["reason"],
                         "SOURCE_MISSING_OR_INVALID")

    def test_missing_source_rows_blocks_pair(self):
        self.assertEqual(run({"status":"READY_RESEARCH", "source":"foo",
             "captured_utc":NOW.isoformat()})["status"], "HOLD")

    def test_not_enough_history_blocks_pair(self):
        data = mock_source(rows=past()[:15]+[future()])
        r = run(data)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["candidate_count"], 0)

    def test_unsupported_league_blocks_before_fetch(self):
        self.assertEqual(run(league="notaleague")["reason"],
                         "UNSUPPORTED_LEAGUE")

    def test_source_fetch_failure_is_hold(self):
        def boom(**kwargs):
            raise TimeoutError("synthetic outage")
        r = capture("epl", boom, clock=Times(NOW, NOW+timedelta(seconds=60)))
        self.assertEqual(r["reason"], "SOURCE_FETCH_FAILED")

    def test_naive_clock_is_hold(self):
        c = Times(datetime(2026, 11, 21, 9))
        r = capture("epl", lambda **kwargs: mock_source(), clock=c)
        self.assertEqual(r["reason"], "INVALID_RUN_CLOCK")

    def test_no_sealed_prospective_evidence_claim_even_if_git_sha(self):
        r = run()
        self.assertEqual(r["git_commit_sha_unverified_metadata"], "a"*40)
        self.assertFalse(r["model_clock_externally_attested"])
        self.assertFalse(r["eligible_for_formal_forward_scoring"])


if __name__ == "__main__":
    unittest.main()
