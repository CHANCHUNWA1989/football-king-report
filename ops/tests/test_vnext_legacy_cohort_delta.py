"""Pure synthetic archive-delta tests. Never authenticate results or release bets."""
from copy import deepcopy
from hashlib import sha1
import json
import unittest

from ops.vnext_legacy_cohort_delta import audit_cohort_delta


def _row(key, *, outcome=1):
    return {
        "key": key,
        "league": "synthetic",
        "market_utc": "2026-11-01T09:00:00Z",
        "forecast_utc": "2026-11-01T10:00:00Z",
        "kickoff_utc": "2026-11-01T12:00:00Z",
        "p": [0.5, 0.3, 0.2],
        "m": [0.4, 0.3, 0.3],
        "y": outcome,
        "fixture_result_source_independently_verified": False,
        "production_recommendations": "DISABLED",
    }


def _archive(rows):
    return {
        "checked_utc": "2026-11-15T08:00:00Z",
        "results_independently_verified": False,
        "profitability_verified": False,
        "production_recommendations": "DISABLED",
        "samples": rows,
    }


def _raw(doc):
    data = json.dumps(doc, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    blob = sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    return data, blob


class LegacyCohortDeltaTests(unittest.TestCase):
    def setUp(self):
        self.old = _archive([_row("case-a"), _row("case-b")])
        self.new = _archive([_row("case-a"), _row("case-b"), _row("case-c")])

    def evaluate(self):
        old_raw, old_sha = _raw(self.old)
        new_raw, new_sha = _raw(self.new)
        return audit_cohort_delta(old_raw, new_raw,
                                  expected_old_git_blob_sha1=old_sha,
                                  expected_new_git_blob_sha1=new_sha)

    def test_clean_append_only_maintains_hold_and_no_certification(self):
        r = self.evaluate()
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["cohort_integrity"], "APPEND_ONLY_BYTES_CONSISTENT_RESEARCH")
        self.assertEqual(r["older_rows"], 2)
        self.assertEqual(r["newer_rows"], 3)
        self.assertEqual(r["unchanged_overlap_rows"], 2)
        self.assertEqual(r["newly_appended_rows"], 1)
        self.assertEqual(r["modified_overlap_rows"], 0)
        self.assertEqual(r["removed_rows"], 0)
        self.assertTrue(r["append_only_verified_between_pinned_archives"])
        self.assertEqual(r["certified_prospective_rows"], 0)
        self.assertFalse(r["independent_result_truth_verified"])
        self.assertFalse(r["commercial_data_rights_verified"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_changed_outcome_is_drift_not_certification(self):
        self.new["samples"][0]["y"] = 2
        r = self.evaluate()
        self.assertEqual(r["cohort_integrity"], "HOLD_HISTORICAL_RECORD_DRIFT")
        self.assertEqual(r["modified_overlap_rows"], 1)
        self.assertFalse(r["append_only_verified_between_pinned_archives"])

    def test_modified_forecast_probabilities_detected(self):
        self.new["samples"][1]["p"] = [0.51, 0.29, 0.2]
        r = self.evaluate()
        self.assertEqual(r["modified_overlap_rows"], 1)
        self.assertEqual(r["cohort_integrity"], "HOLD_HISTORICAL_RECORD_DRIFT")

    def test_modified_provenance_claim_detected(self):
        self.new["samples"][0]["independently_verified"] = True
        r = self.evaluate()
        self.assertEqual(r["modified_overlap_rows"], 1)
        self.assertEqual(r["certified_prospective_rows"], 0)

    def test_reordered_shared_rows_are_not_append_only(self):
        self.new["samples"][:2] = list(reversed(self.new["samples"][:2]))
        r = self.evaluate()
        self.assertEqual(r["modified_overlap_rows"], 0)
        self.assertFalse(r["append_only_verified_between_pinned_archives"])
        self.assertEqual(r["cohort_integrity"], "HOLD_HISTORICAL_RECORD_DRIFT")

    def test_interleaving_new_row_is_not_append_only(self):
        c = self.new["samples"].pop()
        self.new["samples"].insert(1, c)
        r = self.evaluate()
        self.assertEqual(r["newly_appended_rows"], 1)
        self.assertFalse(r["append_only_verified_between_pinned_archives"])

    def test_old_row_removed_detected(self):
        self.new["samples"].pop(0)
        r = self.evaluate()
        self.assertEqual(r["removed_rows"], 1)
        self.assertEqual(r["cohort_integrity"], "HOLD_HISTORICAL_RECORD_DRIFT")

    def test_duplicate_fixture_key_rejected_before_diff(self):
        self.new["samples"].append(deepcopy(self.new["samples"][1]))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ARCHIVED_FIXTURE_KEY"):
            self.evaluate()

    def test_wrong_expected_git_blob_rejected_before_diff(self):
        old_raw, _ = _raw(self.old)
        new_raw, new_sha = _raw(self.new)
        with self.assertRaisesRegex(ValueError, "ARCHIVE_GIT_BLOB_MISMATCH"):
            audit_cohort_delta(old_raw,new_raw,
                expected_old_git_blob_sha1="a"*40,
                expected_new_git_blob_sha1=new_sha)

    def test_same_version_not_misrepresented_as_new_sample_set(self):
        raw, sha = _raw(self.old)
        with self.assertRaisesRegex(ValueError, "IDENTICAL_ARCHIVE_REFERENCES"):
            audit_cohort_delta(raw,raw,
                expected_old_git_blob_sha1=sha,
                expected_new_git_blob_sha1=sha)

    def test_inconsistent_chronology_not_accepted(self):
        self.new["samples"][2]["forecast_utc"] = "2026-11-01T13:00:00Z"
        with self.assertRaisesRegex(ValueError, "INVALID_ARCHIVED_CHRONOLOGY"):
            self.evaluate()

    def test_synthetic_certification_flags_on_new_row_are_not_proof(self):
        self.new["samples"][2]["fixture_result_source_independently_verified"] = True
        self.new["samples"][2]["eligible_for_model_scoring"] = True
        r = self.evaluate()
        self.assertEqual(r["newer_unsupported_certification_claim_rows"], 1)
        self.assertEqual(r["certified_prospective_rows"], 0)
        self.assertEqual(r["status"], "HOLD")

    def test_unmodified_old_field_extra_new_row_may_contain_metadata(self):
        self.new["samples"][2]["source_fixture_identity"] = {
            "provider": "synthetic", "match_id": "x-10"
        }
        r = self.evaluate()
        self.assertEqual(r["newly_appended_rows"],1)
        self.assertEqual(r["modified_overlap_rows"],0)
        self.assertFalse(r["external_witness_independently_verified"])


if __name__ == "__main__":
    unittest.main()
