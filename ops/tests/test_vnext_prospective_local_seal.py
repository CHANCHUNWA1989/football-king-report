"""VNext PR-06: offline synthetic local forecast seal and rights tests."""
import copy
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vnext_prospective_local_seal import (
    audit_source_independence, read_forecast_seal, seal_forecast_pair,
)

KO = "2026-08-01T20:00:00Z"
ASOF = "2026-08-01T18:30:00Z"
NOW = "2026-08-01T18:30:15Z"
SCOPE = "bundesliga/2026-2027/regulation-90-minutes"


def fixture():
    return {
        "fixture_id": "offline-fixture-001", "kickoff_utc": KO, "as_of_utc": ASOF,
        "models": {
            "baseline": {
                "model_id": "baseline-1", "forecast_utc": ASOF,
                "inputs_available_utc": "2026-08-01T18:25:00Z",
                "input_sha256": "a" * 64,
                "probabilities_1x2": [0.45, 0.30, 0.25],
                "calibrated": False, "production_recommendations": "DISABLED",
            },
            "challenger": {
                "model_id": "challenger-1", "forecast_utc": ASOF,
                "inputs_available_utc": "2026-08-01T18:25:00Z",
                "input_sha256": "b" * 64,
                "probabilities_1x2": [0.65, 0.20, 0.15],
                "calibrated": False, "production_recommendations": "DISABLED",
            },
        },
    }


def source():
    return [{
        "provider": "synthetic-forecast-provider", "source_event_id": "event-001",
        "source_group": "unverified-feed",
        "source_updated_utc": "2026-08-01T18:22:00Z",
        "received_utc": "2026-08-01T18:23:00Z",
        "available_utc": "2026-08-01T18:24:00Z",
        "raw_sha256": "c" * 64,
        "rights_scope": "DERIVED_METADATA_ONLY_UNVERIFIED",
    }]


def result_observations(*, score=(2, 1)):
    return [
        {"provider": provider,
         "fixture_id": "offline-fixture-001",
         "provider_fixture_id": "fixture-" + provider,
         "source_scope": SCOPE,
         "home_goals": score[0], "away_goals": score[1],
         "source_updated_utc": "2026-08-01T22:00:00Z",
         "received_utc": "2026-08-01T22:01:00Z",
         "raw_sha256": "d" * 64}
        for provider in ("NDR", "OpenLigaDB")
    ]


def source_audit(rows=None):
    return audit_source_independence(
        result_observations() if rows is None else rows,
        fixture_id="offline-fixture-001", decision_utc="2026-08-01T23:00:00Z")


class LocalSealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_write_one_and_reread_matching_caller_anchor(self):
        s = seal_forecast_pair(self.root, fixture(), source(), captured_utc=NOW)
        self.assertEqual(s["status"], "LOCAL_SEALED_RESEARCH")
        self.assertEqual(s["production_recommendations"], "DISABLED")
        self.assertFalse(s["external_clock_attested"])
        self.assertEqual(len(s["content_sha256"]), 64)
        self.assertEqual((self.root / s["file_name"]).stat().st_mode & 0o777, 0o600)
        recovered = read_forecast_seal(
            self.root, s["file_name"], expected_sha256=s["content_sha256"])
        self.assertEqual(recovered["pair"], fixture())
        self.assertFalse(recovered["results_contained"])
        self.assertFalse(recovered["source_rights_independently_verified"])

    def test_no_overwrite_same_fixture_and_cut(self):
        seal_forecast_pair(self.root, fixture(), source(), captured_utc=NOW)
        with self.assertRaises(FileExistsError):
            seal_forecast_pair(self.root, fixture(), source(), captured_utc=NOW)

    def test_different_fixtures_are_distinct(self):
        p = fixture()
        first = seal_forecast_pair(self.root, p, source(), captured_utc=NOW)
        q = copy.deepcopy(p)
        q["fixture_id"] = "offline-fixture-002"
        second = seal_forecast_pair(self.root, q, source(), captured_utc=NOW)
        self.assertNotEqual(first["file_name"], second["file_name"])

    def test_record_tampering_detected_against_prior_digest(self):
        s = seal_forecast_pair(self.root, fixture(), source(), captured_utc=NOW)
        target = self.root / s["file_name"]
        target.write_bytes(target.read_bytes().replace(b"baseline-1", b"baseline-2"))
        with self.assertRaisesRegex(ValueError, "ARCHIVE_INTEGRITY"):
            read_forecast_seal(self.root, s["file_name"], expected_sha256=s["content_sha256"])

    def test_retroactive_prediction_refused(self):
        with self.assertRaisesRegex(ValueError, "FORECAST_NOT_CAPTURED_PROMPTLY"):
            seal_forecast_pair(
                self.root, fixture(), source(), captured_utc="2026-08-02T19:00:00Z")

    def test_post_kickoff_snapshot_refused(self):
        with self.assertRaises(ValueError):
            seal_forecast_pair(
                self.root, fixture(), source(), captured_utc="2026-08-01T20:00:00Z")

    def test_source_not_available_at_forecast_time_refused(self):
        refs = source()
        refs[0]["available_utc"] = "2026-08-01T18:31:00Z"
        with self.assertRaisesRegex(ValueError, "LATE_SOURCE"):
            seal_forecast_pair(self.root, fixture(), refs, captured_utc=NOW)

    def test_no_forged_license_or_result_fields_in_archive(self):
        refs = source()
        refs[0]["rights_scope"] = "FULL_RAW_REPUBLICATION_LICENSED"
        with self.assertRaisesRegex(ValueError, "INVALID_SOURCE_REFERENCE_OR_RIGHTS"):
            seal_forecast_pair(self.root, fixture(), refs, captured_utc=NOW)
        p = fixture()
        p["fulltime_home_goals"] = 5
        with self.assertRaisesRegex(ValueError, "INVALID_FROZEN_PAIR"):
            seal_forecast_pair(self.root, p, source(), captured_utc=NOW)

    def test_forged_model_calibration_or_post_prediction_inputs_refused(self):
        p = fixture()
        p["models"]["baseline"]["calibrated"] = True
        with self.assertRaises(ValueError):
            seal_forecast_pair(self.root, p, source(), captured_utc=NOW)
        p = fixture()
        p["models"]["baseline"]["inputs_available_utc"] = "2026-08-01T18:35:00Z"
        with self.assertRaises(ValueError):
            seal_forecast_pair(self.root, p, source(), captured_utc=NOW)

    def test_writable_root_and_symlink_root_refused(self):
        os.chmod(self.root, 0o777)
        with self.assertRaisesRegex(ValueError, "INSECURE_ARCHIVE"):
            seal_forecast_pair(self.root, fixture(), source(), captured_utc=NOW)
        os.chmod(self.root, 0o700)
        link = self.root / "link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "INVALID_LOCAL_ARCHIVE"):
            seal_forecast_pair(link, fixture(), source(), captured_utc=NOW)

    def test_symlink_sealed_file_is_never_followed(self):
        s = seal_forecast_pair(self.root, fixture(), source(), captured_utc=NOW)
        real = self.root / s["file_name"]
        copy = self.root / "original"
        real.rename(copy)
        real.symlink_to(copy)
        with self.assertRaises(OSError):
            read_forecast_seal(self.root, s["file_name"],
                               expected_sha256=s["content_sha256"])

    def test_missing_anchor_cannot_verify(self):
        s = seal_forecast_pair(self.root, fixture(), source(), captured_utc=NOW)
        with self.assertRaisesRegex(ValueError, "INVALID_SEAL_REFERENCE"):
            read_forecast_seal(self.root, s["file_name"], expected_sha256="not-an-anchor")

    def test_pair_source_reference_duplicate_holds(self):
        refs = source()
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SOURCE_REFERENCE"):
            seal_forecast_pair(self.root, fixture(), refs * 2, captured_utc=NOW)


class IndependentSourcePolicyTests(unittest.TestCase):
    def test_two_matching_provider_displays_remain_unverified(self):
        report = source_audit()
        self.assertEqual(report["status"], "HOLD")
        self.assertTrue(report["observation_agreement"])
        self.assertEqual(report["providers"], ["NDR", "OpenLigaDB"])
        self.assertEqual(report["reason"], "AGREED_UNVERIFIED_UPSTREAM_AND_LICENSE_SCOPE")
        self.assertFalse(report["independent_result_authentication"])
        self.assertFalse(report["source_independence_authenticated"])
        self.assertFalse(report["licensed_data_rights_verified"])
        self.assertFalse(report["model_scoring_eligible"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_same_provider_twice_not_an_independent_source(self):
        rows = result_observations()
        rows[1]["provider"] = "NDR"
        self.assertEqual(source_audit(rows)["reason"], "DUPLICATE_PROVIDER")

    def test_conflicting_final_score_not_promoted(self):
        rows = result_observations()
        rows[1]["home_goals"] = 3
        r = source_audit(rows)
        self.assertEqual(r["reason"], "RESULT_SOURCE_SCORE_CONFLICT")
        self.assertFalse(r["observation_agreement"])

    def test_out_of_scope_season_and_source_refused(self):
        rows = result_observations()
        rows[0]["source_scope"] = "ucl/2026-2027/regulation-90-minutes"
        self.assertFalse(source_audit(rows)["observation_agreement"])
        rows = result_observations()
        rows[1]["provider"] = "unlisted-provider"
        self.assertFalse(source_audit(rows)["observation_agreement"])

    def test_caller_true_authorization_flag_does_not_certify(self):
        rows = result_observations()
        rows[0]["independently_verified"] = True
        self.assertEqual(source_audit(rows)["reason"], "INVALID_RESULT_SOURCE_SCHEMA")

    def test_future_received_source_is_rejected(self):
        rows = result_observations()
        rows[0]["received_utc"] = "2026-08-02T01:00:00Z"
        self.assertEqual(source_audit(rows)["reason"], "SOURCE_RESULT_NOT_AVAILABLE")

    def test_policy_is_fixed_and_cannot_be_supplied_by_caller(self):
        rows = result_observations()
        rows[0]["policy_override"] = "ASSUME_LICENSED"
        self.assertEqual(source_audit(rows)["status"], "HOLD")

    def test_numerical_false_positive_bool_goals_rejected(self):
        rows = result_observations()
        rows[0]["home_goals"] = True
        self.assertFalse(source_audit(rows)["observation_agreement"])


if __name__ == "__main__":
    unittest.main()
