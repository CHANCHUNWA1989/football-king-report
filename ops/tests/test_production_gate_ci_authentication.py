"""Fail-closed research bootstrap interval and production-admission tests.

All cases below are synthetic. No real result, executable odds, source
authentication, forecast uplift, or positive EV is asserted.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from production_gate import gate


class ProductionIntervalAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.center = {
            "production_recommendations": "DISABLED",
            "six_league_result_verification_complete": False,
            "market_odds_are_executable": False,
        }
        self.evidence = {
            "production_recommendations": "DISABLED",
            "samples": [],
            "n": 0,
        }
        self.validation = {
            "production_recommendations": "DISABLED",
            "status": "HOLD",
            "immutable_forecast_evidence_verified": False,
            "measurements": None,
        }

    def report(self, interval):
        self.validation["measurements"] = {
            "difference_block_bootstrap_95pct_ci": interval,
        }
        return gate(self.center, self.evidence, self.validation)

    def assert_held(self, result):
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["conditions"][
            "positive_week_block_bootstrap_lower_ci_against_market"])
        self.assertEqual(result["authenticated_forward_samples"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["ready_for_independent_review"])

    def test_valid_synthetic_research_ci_does_not_qualify_production(self):
        result = self.report([0.1, 0.3])
        self.assert_held(result)
        self.assertTrue(result[
            "research_only_positive_bootstrap_ci_unverified"])
        self.assertFalse(result[
            "research_bootstrap_ci_independently_authenticated"])

    def test_invalid_or_non_finite_intervals_never_claim_positive(self):
        for interval in (
            [0.3, 0.1], [float("inf"), float("inf")],
            [0.1, float("nan")], [float("-inf"), 2],
            [True, 0.3], ["0.2", 0.3], [0.3],
            [0.1, 0.3, 0.5], None, [], {},
            [0.0, 0.4], [-0.1, 0.3],
        ):
            with self.subTest(interval=repr(interval)):
                result = self.report(interval)
                self.assert_held(result)
                self.assertFalse(result[
                    "research_only_positive_bootstrap_ci_unverified"])

    def test_self_reported_certification_flags_do_not_change_requirement(self):
        self.center.update(
            six_league_result_verification_complete=True,
            market_odds_are_executable=True,
            risk_adjusted_roi_and_clv_independently_verified=True,
        )
        self.validation.update(
            immutable_forecast_evidence_verified=True,
            signature_identity_and_subject_verified=True,
            independently_verified_result_count=300,
            authenticated_forward_samples=300,
            independent_manual_research_approval=True,
        )
        result = self.report([0.1, 0.3])
        self.assert_held(result)
        self.assertTrue(result[
            "research_only_positive_bootstrap_ci_unverified"])
        self.assertFalse(result[
            "research_bootstrap_ci_independently_authenticated"])
        self.assertFalse(result["conditions"]["independent_manual_research_approval"])
        self.assertFalse(result["automated_release_supported"])

    def test_malformed_measurement_objects_fail_closed(self):
        for measurements in ("untrusted", [0.1, 0.3], True, 12, object()):
            with self.subTest(measurements=repr(measurements)):
                self.validation["measurements"] = measurements
                result = gate(self.center, self.evidence, self.validation)
                self.assert_held(result)
                self.assertFalse(result[
                    "research_only_positive_bootstrap_ci_unverified"])


if __name__ == "__main__":
    unittest.main()
