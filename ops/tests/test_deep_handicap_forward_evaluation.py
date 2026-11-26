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

    def test_uncertainty_small_cohort_and_empty_calibration(self):
        out = evaluate([row()],as_of_utc=NOW)
        cohort = out["cohorts"]["SYNTHETIC"]
        self.assertEqual(cohort["paired_uncertainty"]["status"],"INSUFFICIENT_SAMPLE")
        self.assertIsNone(cohort["paired_uncertainty"]["intervals"])
        bins = cohort["full_win_calibration"]["bins"]["baseline"]
        self.assertEqual(sum(b["n"] for b in bins),1)
        self.assertIsNone(bins[0]["observed_fraction"])

    def test_week_cluster_bootstrap_reproducible_and_separate(self):
        from datetime import datetime, timedelta, timezone
        start = datetime(2026,1,5,12,tzinfo=timezone.utc)
        rows = []
        for w in range(12):
            for j in range(25):
                r = row(f"w{w}-f{j}")
                ko = start + timedelta(weeks=w, minutes=j)
                cutoff = (ko-timedelta(minutes=30)).isoformat()
                r.update(kickoff_utc=ko.isoformat(), information_cutoff_utc=cutoff)
                for name in ("baseline","challenger"):
                    r[name].update(kickoff_utc=ko.isoformat(), information_cutoff_utc=cutoff,
                                   recorded_utc=(ko-timedelta(minutes=25)).isoformat())
                for obs in r["results"]:
                    obs.update(kickoff_utc=ko.isoformat(), captured_utc=(ko+timedelta(hours=2)).isoformat(),
                               score_ft=[3,0] if w%3 else [1,0])
                rows.append(r)
        now = "2026-05-01T00:00:00Z"
        a = evaluate(rows,as_of_utc=now)
        b = evaluate(list(reversed(rows)),as_of_utc=now)
        c = a["cohorts"]["SYNTHETIC"]
        u = c["paired_uncertainty"]
        self.assertEqual(u["status"],"DESCRIPTIVE_INTERVAL_ONLY")
        self.assertEqual(u["utc_iso_week_count"],12)
        self.assertEqual(u["bootstrap_replicates"],2000)
        self.assertEqual(u,b["cohorts"]["SYNTHETIC"]["paired_uncertainty"])
        for metric in ("multiclass_brier","log_loss"):
            interval = u["intervals"][metric+"_delta"]
            self.assertLessEqual(interval["lower"], interval["upper"])
            self.assertAlmostEqual(u["point_estimate"][metric+"_delta"],
                                   c["overall"]["paired_delta"][metric])
        self.assertEqual(a["true_forward_sample_count"],0)
        self.assertFalse(a["confidence_interval_available"])
        self.assertIsNone(a["cohorts"]["EXTERNAL_UNAUTHENTICATED"]["paired_uncertainty"]["intervals"])

    def test_mixed_model_versions_reject_uncertainty(self):
        r = row("second")
        r["challenger"]["model_id"] = "other-version"
        out = evaluate([row(),r],as_of_utc=NOW)
        u = out["cohorts"]["SYNTHETIC"]["paired_uncertainty"]
        self.assertEqual(u["status"],"MIXED_MODEL_VERSIONS")
        self.assertIsNone(u["intervals"])
