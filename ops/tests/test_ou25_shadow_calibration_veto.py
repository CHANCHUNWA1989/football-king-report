import copy
import unittest

from ops.ou25_shadow_calibration_veto import audit

SOURCE = "e6744429ee395bc86f247348c6184bb08d4eb361"
BASELINE = {
    "probability_over25": 0.55,
    "training_end_date": "2024-12-31",
    "sample_count": 380,
    "source": "training-season-fixed",
}


def rows(prefix, date, outcome, probability=0.4):
    return [{"league": "test_league", "fixture_id": f"{prefix}-{i:03d}",
             "match_date": date, "original_over25_probability": probability,
             "actual_over25": outcome} for i in range(80)]


class OU25ShadowCalibrationVetoTests(unittest.TestCase):
    def test_correct_challenger_math_never_promotes(self):
        v = rows("val", "2025-05-01", 1)
        t = rows("test", "2026-05-01", 1)
        r = audit(v, t, baseline=BASELINE, source_revision=SOURCE)
        self.assertGreater(r["challenger_brier_better_than_original"], 0)
        self.assertLess(r["challenger"]["brier"], r["original"]["brier"])
        self.assertEqual(r["research_veto"], "HOLD_INDEPENDENT_FORWARD_ATTESTATION_REQUIRED")
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["eligible_for_promotion"])
        self.assertFalse(r["source_and_result_independently_authenticated"])
        self.assertFalse(r["betting_ev_verified"])

    def test_unseen_reverse_outcomes_veto_worse_challenger(self):
        v = rows("val", "2025-05-01", 1)
        t = rows("test", "2026-05-01", 0)
        r = audit(v, t, baseline=BASELINE, source_revision=SOURCE)
        self.assertGreater(r["challenger"]["brier"], r["original"]["brier"])
        self.assertEqual(r["research_veto"], "REJECT_WORSE_THAN_ORIGINAL")
        self.assertFalse(r["eligible_for_promotion"])

    def test_training_validation_must_precede_holdout(self):
        v = rows("val", "2026-05-01", 1)
        t = rows("test", "2026-05-01", 0)
        with self.assertRaisesRegex(ValueError, "VALIDATION_NOT_STRICTLY_BEFORE_HELDOUT"):
            audit(v, t, baseline=BASELINE, source_revision=SOURCE)

    def test_no_duplicate_or_overlap_fixture(self):
        v = rows("val", "2025-05-01", 1)
        t = rows("test", "2026-05-01", 1)
        v[1] = copy.deepcopy(v[0])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_FIXTURE_ID"):
            audit(v, t, baseline=BASELINE, source_revision=SOURCE)
        v = rows("val", "2025-05-01", 1)
        t[0]["fixture_id"] = v[0]["fixture_id"]
        with self.assertRaisesRegex(ValueError, "OVERLAPPING_FIXTURES"):
            audit(v, t, baseline=BASELINE, source_revision=SOURCE)

    def test_future_or_invalid_training_baseline_rejected(self):
        v = rows("val", "2025-05-01", 1)
        t = rows("test", "2026-05-01", 1)
        base = {**BASELINE, "training_end_date": "2026-05-01"}
        with self.assertRaisesRegex(ValueError, "BASELINE_NOT_BEFORE_HELDOUT"):
            audit(v, t, baseline=base, source_revision=SOURCE)
        base = {**BASELINE, "probability_over25": True}
        with self.assertRaisesRegex(ValueError, "INVALID_PROBABILITY"):
            audit(v, t, baseline=base, source_revision=SOURCE)
        base = {**BASELINE, "sample_count": True}
        with self.assertRaisesRegex(ValueError, "INVALID_TRAINING_BASELINE_PROVENANCE"):
            audit(v, t, baseline=base, source_revision=SOURCE)

    def test_bad_probabilities_labels_dates_and_source_rejected(self):
        v = rows("val", "2025-05-01", 1)
        t = rows("test", "2026-05-01", 1)
        v[0]["original_over25_probability"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_PROBABILITY"):
            audit(v, t, baseline=BASELINE, source_revision=SOURCE)
        v = rows("val", "2025-05-01", 1)
        v[0]["actual_over25"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_ACTUAL_OVER25"):
            audit(v, t, baseline=BASELINE, source_revision=SOURCE)
        v = rows("val", "2025-05-01", 1)
        v[0]["match_date"] = "2025-02-30"
        with self.assertRaisesRegex(ValueError, "INVALID_DATE"):
            audit(v, t, baseline=BASELINE, source_revision=SOURCE)
        v = rows("val", "2025-05-01", 1)
        with self.assertRaisesRegex(ValueError, "INVALID_SOURCE_REVISION"):
            audit(v, t, baseline=BASELINE, source_revision="mutable-branch")

    def test_small_selected_cohort_not_accepted(self):
        v = rows("val", "2025-05-01", 1)[:79]
        t = rows("test", "2026-05-01", 1)
        with self.assertRaisesRegex(ValueError, "INVALID_VALIDATION_SIZE"):
            audit(v, t, baseline=BASELINE, source_revision=SOURCE)
        v = rows("val", "2025-05-01", 1)
        with self.assertRaisesRegex(ValueError, "INVALID_HELDOUT_SIZE"):
            audit(v, t[:79], baseline=BASELINE, source_revision=SOURCE)

    def test_input_records_not_mutated(self):
        v = rows("val", "2025-05-01", 0)
        t = rows("test", "2026-05-01", 1)
        before = copy.deepcopy((v, t, BASELINE))
        audit(v, t, baseline=BASELINE, source_revision=SOURCE)
        self.assertEqual((v, t, BASELINE), before)


if __name__ == "__main__":
    unittest.main()
