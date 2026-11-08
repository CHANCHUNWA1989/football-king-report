"""All-synthetic, outcome-blind pre-kickoff same-snapshot model identity A/B tests."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ops import identity_ab_compare as ab


NOW = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)
FORECAST = "2026-10-10T12:00:00+00:00"


def history(*, split=True):
    rows = []
    for i in range(36):
        # Distinct past dates: scores are SYNTHETIC and never claimed real.
        left = "Manchester City" if i < 18 or not split else "Man City"
        score = [4, 0] if i < 18 else [0, 2]
        rows.append({
            "date": (NOW - timedelta(days=i+1)).date().isoformat(),
            "home": left, "away": "Arsenal",
            "score_ft": score, "status": "FINISHED", "kickoff_utc": None,
        })
    return rows


def fixture(*, home="Man City", away="Arsenal", eid="event-001", ko=FORECAST):
    return {
        "date": "2026-10-10", "home": home, "away": away,
        "kickoff_utc": ko, "event_id": eid,
        "score_ft": None, "status": "SCHEDULED",
    }


def snapshot(*, split=True):
    return history(split=split) + [fixture()]


class IdentityAbComparatorTests(unittest.TestCase):
    def test_same_source_snapshot_generates_actual_comparable_probability_change(self):
        rows = snapshot()
        original = copy.deepcopy(rows)
        report = ab.compare(rows, league="epl", as_of_utc=NOW.isoformat(),
                            source_commit="a"*40)
        self.assertEqual(rows, original)
        self.assertEqual(report["counts"]["legacy"], 1)
        self.assertEqual(report["counts"]["candidate"], 1)
        self.assertEqual(report["counts"]["paired"], 1)
        self.assertEqual(report["counts"]["legacy_only"], 0)
        self.assertEqual(report["counts"]["candidate_only"], 0)
        self.assertGreater(report["counts"]["mean_abs_home_probability_delta"], 0)
        self.assertEqual(report["paired"][0]["event_id"], "event-001")
        self.assertEqual(report["paired"][0]["kickoff_utc"], FORECAST)
        self.assertFalse(report["paired"][0]["comparison_has_result_outcome"])
        self.assertFalse(report["model_accuracy_improved_proven"])
        self.assertFalse(report["market_benchmark_beaten"])
        self.assertFalse(report["positive_ev_verified"])
        self.assertEqual(report["certified_case_count"], 0)
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_exact_same_names_original_model_has_same_probabilities(self):
        rows = history(split=False) + [fixture(home="Manchester City")]
        report = ab.compare(rows, league="epl", as_of_utc=NOW.isoformat())
        self.assertEqual(report["counts"]["paired"], 1)
        self.assertEqual(report["paired"][0]["legacy_1x2"],
                         report["paired"][0]["candidate_1x2"])
        self.assertEqual(report["counts"]["mean_abs_home_probability_delta"], 0)

    def test_candidate_only_research_case_is_counted_not_cherry_picked(self):
        rows = history() + [fixture(home="Manchester City FC", away="Arsenal FC")]
        report = ab.compare(rows, league="epl", as_of_utc=NOW.isoformat())
        self.assertEqual(report["counts"]["legacy"], 0)
        self.assertEqual(report["counts"]["candidate"], 1)
        self.assertEqual(report["counts"]["paired"], 0)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(len(report["candidate_only"]), 1)

    def test_non_matches_kept_in_coverage_counts(self):
        rows = history() + [fixture(eid="match-1"),
                            fixture(eid="match-2", away="Arsenal FC",
                                    home="Manchester City FC",
                                    ko="2026-10-11T13:00:00+00:00")]
        report = ab.compare(rows, league="epl", as_of_utc=NOW.isoformat())
        self.assertEqual(report["counts"]["legacy"], 1)
        self.assertEqual(report["counts"]["candidate"], 2)
        self.assertEqual(report["counts"]["paired"], 1)
        self.assertEqual(report["counts"]["candidate_only"], 1)

    def test_no_future_outcome_may_enter_prospective_snapshot(self):
        for bad in ({"score_ft":[5, 0]}, {"outcome":0}, {"settlement":{"y":1}}):
            rows = history() + [{**fixture(), **bad}]
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError,
                                            "POST_KICKOFF_OR_FUTURE_RESULT_LEAKAGE"):
                    ab.compare(rows, league="epl", as_of_utc=NOW.isoformat())
        rows = history()
        rows[0]["date"] = "2026-10-09"
        with self.assertRaisesRegex(ValueError, "RESULT_LEAKAGE"):
            ab.compare(rows+[fixture()], league="epl", as_of_utc=NOW.isoformat())

    def test_malformed_clocks_and_league_and_commit_refuse(self):
        rows = snapshot()
        for argument in ("2026-10-09T04:00:00", "bad clock"):
            with self.subTest(argument=argument):
                with self.assertRaises(ValueError):
                    ab.compare(rows, league="epl", as_of_utc=argument)
        with self.assertRaisesRegex(ValueError,"INVALID_AB_INPUT"):
            ab.compare(rows, league="mls", as_of_utc=NOW.isoformat())
        with self.assertRaisesRegex(ValueError,"INVALID_AB_SOURCE_COMMIT"):
            ab.compare(rows, league="epl", as_of_utc=NOW.isoformat(),
                       source_commit="not-a-hash")

    def test_same_input_digest_stable_and_timestamp_pinned(self):
        rows = snapshot()
        a = ab.compare(rows, league="epl", as_of_utc=NOW.isoformat())
        b = ab.compare(rows, league="epl", as_of_utc=NOW.isoformat())
        self.assertEqual(a, b)
        self.assertEqual(a["input_canonical_sha256"], b["input_canonical_sha256"])
        self.assertEqual(a["as_of_utc"], NOW.isoformat())
        self.assertEqual(a["frozen_legacy_source_blob_sha1"], ab.frozen.SOURCE_BLOB)
        changed = copy.deepcopy(rows)
        changed[0]["score_ft"] = [3, 1]
        c = ab.compare(changed, league="epl", as_of_utc=NOW.isoformat())
        self.assertNotEqual(c["input_canonical_sha256"], a["input_canonical_sha256"])

    def test_never_consider_forged_betting_or_calibration_authority(self):
        rows = snapshot()
        original = ab.candidate_predict
        for changed in ({"production_recommendations": "ENABLED"},
                        {"verified_market_odds": True},
                        {"calibrated": True},
                        {"training_identity_method":"untrusted"}):
            with self.subTest(changed=changed):
                def tampered(*args, **kwargs):
                    result = original(*args, **kwargs)
                    for item in result:
                        item.update(changed)
                    return result
                with patch.object(ab, "candidate_predict", side_effect=tampered):
                    with self.assertRaisesRegex(ValueError, "AB_FORECAST_UNSAFE|AB_CANDIDATE"):
                        ab.compare(rows, league="epl", as_of_utc=NOW.isoformat())

    def test_forged_candidate_identity_cannot_join_original_fixture(self):
        rows = snapshot()
        original = ab.candidate_predict
        def modified(*args, **kwargs):
            result = original(*args, **kwargs)
            for item in result:
                item["home"] = "Arsenal"
            return result
        with patch.object(ab,"candidate_predict",side_effect=modified):
            with self.assertRaisesRegex(ValueError, "AB_FIXTURE_IDENTITY_MISMATCH"):
                ab.compare(rows, league="epl", as_of_utc=NOW.isoformat())

    def test_mutating_an_engine_input_is_rejected(self):
        original=ab.candidate_predict
        rows=snapshot()
        def malicious(input_rows, league, now):
            input_rows[0]["score_ft"] = [9, 9]
            return original(input_rows,league,now)
        with patch.object(ab, "candidate_predict", side_effect=malicious):
            with self.assertRaisesRegex(ValueError, "AB_INPUT_MUTATED_BY_MODEL"):
                ab.compare(rows, league="epl", as_of_utc=NOW.isoformat())

    def test_cli_no_outcome_or_market_edge_claim(self):
        with TemporaryDirectory() as folder:
            input_path = Path(folder)/"snapshot.json"
            input_path.write_text(json.dumps({
                "schema":ab.INPUT_SCHEMA,
                "league":"epl",
                "as_of_utc":NOW.isoformat(),
                "rows":snapshot(),
            }),encoding="utf-8")
            result=subprocess.run(
                [sys.executable,"-m","ops.identity_ab_compare","--input",str(input_path),
                 "--source-commit","b"*40],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+" "+result.stderr)
            report=json.loads(result.stdout)
            self.assertEqual(report["counts"]["paired"],1)
            self.assertFalse(report["model_accuracy_improved_proven"])
            self.assertFalse(report["positive_ev_verified"])
            self.assertEqual(report["production_recommendations"],"DISABLED")
            self.assertNotIn("recommendations", report["paired"][0])


if __name__=="__main__":
    unittest.main()
