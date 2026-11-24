"""Synthetic-only regression of the independent time-locked research calibration gate."""
import copy
import math
import unittest
from datetime import datetime, timedelta, timezone

from ops.prospective_temperature_challenger import (
    compare, MIN_TRAIN, MIN_VALIDATION, _temperature, TEMPERATURES,
)

UTC = timezone.utc
START = datetime(2026, 1, 1, 12, tzinfo=UTC)
CUTOFF = START + timedelta(days=170)


def stamp(value):
    return value.isoformat()


def record(index, *, probs=None, outcome=None):
    kick = START + timedelta(days=index)
    return {
        "league": "bundesliga",
        "source_event_id": f"synthetic:de:case-{index}",
        "forecast_utc": stamp(kick - timedelta(hours=24)),
        "kickoff_utc": stamp(kick),
        "settled_utc": stamp(kick + timedelta(hours=3)),
        "p": [0.82, 0.10, 0.08] if probs is None else list(probs),
        "y": (0 if index % 4 == 0 else 1 if index % 4 == 1 else 2)
        if outcome is None else outcome,
        # Only synthetic test assertions, not real external authentication.
        "forecast_provenance_independently_attested": True,
        "fixture_result_source_independently_verified": True,
        "fixture_identity_independently_verified": True,
        "production_recommendations": "DISABLED",
    }


def fixtures():
    return [record(i) for i in range(160)]


def upcoming():
    return {
        "league": "bundesliga",
        "source_event_id": "synthetic:de:future",
        "forecast_utc": stamp(CUTOFF - timedelta(minutes=30)),
        "kickoff_utc": stamp(CUTOFF + timedelta(days=2)),
        "p": [0.8, 0.12, 0.08],
        "production_recommendations": "DISABLED",
    }


def run(rows=None, candidate=None):
    return compare(fixtures() if rows is None else rows,
                   upcoming() if candidate is None else candidate,
                   as_of_utc=stamp(CUTOFF))


class TimeLockedTemperatureChallengerTests(unittest.TestCase):
    def test_reduces_overconfidence_only_in_research(self):
        result = run()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertGreaterEqual(result["train_count"], MIN_TRAIN)
        self.assertGreaterEqual(result["validation_count"], MIN_VALIDATION)
        self.assertGreater(result["fitted_temperature"], 1.0)
        self.assertLess(result["validation_challenger"]["log_loss"],
                        result["validation_original"]["log_loss"])
        self.assertLess(result["validation_challenger"]["brier"],
                        result["validation_original"]["brier"])
        data = result["candidate"]
        self.assertLess(data["calibrated_research_probabilities"][0], 0.8)
        self.assertGreater(data["calibrated_research_probabilities"][1], 0.12)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["model_promoted"])
        self.assertFalse(data["betting_eligible"])
        self.assertFalse(data["verified_out_of_sample_improvement"])
        self.assertFalse(result["external_attestation_verified_by_this_module"])

    def test_public_finite_grid_preserves_probability_mass(self):
        for t in TEMPERATURES:
            p = _temperature((0.8, .1, .1), t)
            self.assertAlmostEqual(math.fsum(p), 1.0, places=13)
            self.assertTrue(all(0 < x < 1 for x in p))
        self.assertAlmostEqual(_temperature((.8, .1, .1), 1.0)[0], .8, places=13)

    def test_deterministic_under_input_permutation(self):
        rows = fixtures()
        self.assertEqual(run(rows), run(list(reversed(rows))))

    def test_unverified_legacy_settlements_cannot_train(self):
        rows = fixtures()
        for row in rows:
            row["fixture_result_source_independently_verified"] = False
        result = run(rows)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "INSUFFICIENT_INDEPENDENT_PREMATCH_HISTORY")
        self.assertEqual(result["admitted_before_candidate"], 0)
        self.assertEqual(result["rejected_unverified"], 160)

    def test_future_settlement_cannot_leak_in_even_when_claimed_verified(self):
        rows = fixtures()
        forged = record(171)
        # Result occurs after candidate forecast; do not use it.
        self.assertEqual(run(rows), run(rows + [forged]))

    def test_duplicate_event_identity_fails_closed(self):
        rows = fixtures()
        result = run(rows + [copy.deepcopy(rows[0])])
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "DUPLICATE_OR_CANDIDATE_RESULT_ID")

    def test_candidate_identity_cannot_appear_in_training(self):
        rows = fixtures()
        rows[10]["source_event_id"] = upcoming()["source_event_id"]
        self.assertEqual(run(rows)["reason"], "DUPLICATE_OR_CANDIDATE_RESULT_ID")

    def test_claimed_verified_outcome_cannot_be_boolean(self):
        rows = fixtures()
        rows[15]["y"] = True
        self.assertEqual(run(rows)["reason"], "INVALID_OUTCOME")

    def test_malformed_input_not_silently_accepted(self):
        rows = fixtures()
        rows[8]["p"] = [.75, .15, .15]
        self.assertEqual(run(rows)["reason"], "NOT_NORMALIZED")
        rows = fixtures()
        rows[8]["p"] = [float("nan"), .1, .1]
        self.assertEqual(run(rows)["reason"], "INVALID_PROBABILITIES")

    def test_results_in_candidate_cannot_create_hindsight_forecast(self):
        for extra in ({"y": 1}, {"score_ft": None}, {"result": "1-1"}):
            candidate = {**upcoming(), **extra}
            self.assertEqual(run(candidate=candidate)["reason"],
                             "CANDIDATE_CONTAINS_RESULT")

    def test_postkickoff_or_naive_forecast_denied(self):
        candidate = upcoming()
        candidate["kickoff_utc"] = stamp(CUTOFF - timedelta(seconds=1))
        self.assertEqual(run(candidate=candidate)["reason"],
                         "CANDIDATE_NOT_STRICTLY_PREMATCH")
        candidate = upcoming()
        candidate["forecast_utc"] = "2026-01-01T00:00:00"
        self.assertEqual(run(candidate=candidate)["reason"], "NAIVE_TIMESTAMP")

    def test_train_must_be_settled_before_first_validation_forecast(self):
        rows = fixtures()
        # Every training score is only made available after holdout started.
        for row in rows[:120]:
            row["settled_utc"] = stamp(START + timedelta(days=161))
        result = run(rows)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn(result["reason"], (
            "INSUFFICIENT_INDEPENDENT_PREMATCH_HISTORY",
            "TRAIN_SETTLEMENT_NOT_PRIOR_TO_VALIDATION",
        ))

    def test_short_span_rejected_even_when_n_is_large(self):
        rows = fixtures()
        for i, row in enumerate(rows):
            kick = START + timedelta(hours=i)
            row["forecast_utc"] = stamp(kick - timedelta(minutes=30))
            row["kickoff_utc"] = stamp(kick)
            row["settled_utc"] = stamp(kick + timedelta(hours=2))
        result = run(rows)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "INSUFFICIENT_TEMPORAL_COVERAGE")

    def test_impossibly_early_regulation_result_cannot_train(self):
        rows = fixtures()
        for row in rows:
            kick = datetime.fromisoformat(row["kickoff_utc"])
            row["settled_utc"] = stamp(kick + timedelta(minutes=89, seconds=59))
        result = run(rows)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["admitted_before_candidate"], 0)

    def test_exact_regulation_elapsed_boundary_is_admissible_research(self):
        rows = fixtures()
        for row in rows:
            kick = datetime.fromisoformat(row["kickoff_utc"])
            row["settled_utc"] = stamp(kick + timedelta(minutes=90))
        result = run(rows)
        self.assertEqual(result["admitted_before_candidate"], 160)
        self.assertFalse(result["eligible_for_formal_forward_scoring"])

    def test_same_kickoff_group_entirely_in_validation(self):
        rows = fixtures()
        kick = datetime.fromisoformat(rows[119]["kickoff_utc"])
        for row in rows[119:122]:
            row["kickoff_utc"] = stamp(kick)
            row["forecast_utc"] = stamp(kick - timedelta(hours=24))
            row["settled_utc"] = stamp(kick + timedelta(hours=3))
        result = run(rows)
        self.assertEqual(result["validation_count"], 41)
        self.assertGreaterEqual(result["train_count"], MIN_TRAIN)
        self.assertEqual(result, run(list(reversed(rows))))
        self.assertFalse(result["eligible_for_formal_forward_scoring"])

    def test_already_calibrated_sample_should_not_be_recalibrated(self):
        rows = fixtures()
        for i, row in enumerate(rows):
            row["p"] = [.4, .3, .3]
            row["y"] = 0 if i % 10 < 4 else 1 if i % 10 < 7 else 2
        result = run(rows)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "NO_CONSISTENT_VALIDATION_IMPROVEMENT")
        self.assertIsNone(result["candidate"])

    def test_absent_evidence_does_not_produce_a_prediction(self):
        result = run([])
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["eligible_for_formal_forward_scoring"])


if __name__ == "__main__":
    unittest.main()
