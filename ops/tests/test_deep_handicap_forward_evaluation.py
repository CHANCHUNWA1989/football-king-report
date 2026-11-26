"""Synthetic checks only; no fixtures count as authenticated forward data."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deep_handicap_forward_evaluation import evaluate

NOW = "2026-01-02T00:00:00Z"


def row(fid="sample1", kind="SYNTHETIC"):
    identity = dict(league_id="test", fixture_id=fid, home_id="home",
                    away_id="away", kickoff_utc="2026-01-01T12:00:00Z")
    line = dict(side="HOME", handicap=-2.25,
                information_cutoff_utc="2026-01-01T11:30:00Z")
    r = dict(**identity, **line, data_kind=kind)
    for name, p in (("baseline", .3), ("challenger", .6)):
        r[name] = dict(**identity, **line, model_id=name, archive_reference="synthetic",
                       recorded_utc="2026-01-01T11:35:00Z",
                       probabilities=dict(FULL_WIN=p, HALF_WIN=0, PUSH=0,
                                          HALF_LOSS=.1, FULL_LOSS=.9-p))
    r["results"] = [dict(**identity, provider_id=provider,
                         evidence_reference="synthetic", status="FINISHED_90_MINUTES",
                         captured_utc="2026-01-01T14:00:00Z", score_ft=[3,0])
                    for provider in ("source1","source2")]
    return r


class DeepForwardTests(unittest.TestCase):
    def test_scores_and_separate_cohorts(self):
        out = evaluate([row(),row("sample2","EXTERNAL_UNAUTHENTICATED")],as_of_utc=NOW)
        for kind in ("SYNTHETIC","EXTERNAL_UNAUTHENTICATED"):
            stats = out["cohorts"][kind]["overall"]
            self.assertEqual(stats["n"],1)
            self.assertEqual(stats["grades"]["FULL_WIN"],1)
            self.assertLess(stats["paired_delta"]["multiclass_brier"],0)
            self.assertLess(stats["paired_delta"]["log_loss"],0)
        self.assertEqual(out["true_forward_sample_count"],0)
        self.assertFalse(out["accuracy_improvement_verified"])
        self.assertEqual(out["production_recommendations"],"DISABLED")

    def test_duplicate_all_rejected(self):
        out = evaluate([row(),row()],as_of_utc=NOW)
        self.assertEqual(out["rejected"]["DUPLICATE_FIXTURE"],2)
        self.assertEqual(out["cohorts"]["SYNTHETIC"]["overall"]["n"],0)

    def test_temporal_identity_and_conflict_guards(self):
        cases = [
            ("PREDICTION_NOT_PREMATCH", lambda r: r["challenger"].update(recorded_utc="2026-01-01T12:01:00Z")),
            ("UNEQUAL_INFORMATION_CUTOFF", lambda r: r["challenger"].update(information_cutoff_utc="2026-01-01T11:31:00Z")),
            ("PREDICTION_IDENTITY_MISMATCH", lambda r: r["challenger"].update(handicap=-2)),
            ("RESULT_IDENTITY_MISMATCH", lambda r: r["results"][0].update(fixture_id="wrong")),
            ("CONFLICTING_RESULT_CLAIMS", lambda r: r["results"][1].update(score_ft=[2,0])),
            ("DUPLICATE_RESULT_PROVIDER", lambda r: r["results"][1].update(provider_id="source1")),
            ("RESULT_TIME_INVALID", lambda r: r["results"][0].update(captured_utc="2026-01-03T00:00:00Z")),
            ("NOT_REGULATION_FINAL", lambda r: r["results"][0].update(status="AFTER_EXTRA_TIME")),
        ]
        for reason, mutate in cases:
            r = row()
            mutate(r)
            with self.subTest(reason=reason):
                out = evaluate([r],as_of_utc=NOW)
                self.assertEqual(out["rejected"].get(reason),1)
                self.assertEqual(out["cohorts"]["SYNTHETIC"]["overall"]["n"],0)

    def test_invalid_probability_and_impossible_grade(self):
        for p, reason in [(float("nan"),"BAD_PROBABILITY"),(True,"BAD_PROBABILITY"),(.5,"BAD_PROBABILITY_MASS")]:
            r = row()
            r["baseline"]["probabilities"]["FULL_WIN"] = p
            self.assertEqual(evaluate([r],as_of_utc=NOW)["rejected"].get(reason),1)
        r = row()
        r["baseline"]["probabilities"].update(PUSH=.1,HALF_LOSS=0)
        self.assertEqual(evaluate([r],as_of_utc=NOW)["rejected"].get("IMPOSSIBLE_GRADE_MASS"),1)

    def test_empty_is_hold_not_zero_loss(self):
        out = evaluate([],as_of_utc=NOW)
        self.assertEqual(out["status"],"HOLD")
        self.assertIsNone(out["cohorts"]["SYNTHETIC"]["overall"]["baseline"])

    def test_half_loss_settlement(self):
        r = row()
        for obs in r["results"]:
            obs["score_ft"] = [2,0]
        out = evaluate([r],as_of_utc=NOW)
        self.assertEqual(out["cohorts"]["SYNTHETIC"]["overall"]["grades"]["HALF_LOSS"],1)
