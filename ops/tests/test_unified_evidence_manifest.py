import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_evidence_manifest import manifest, mobile_report


def fixtures():
    return (
        [{"fixture_id": '["epl","A","B","2026-10-16"]', "production_recommendations": "DISABLED"}],
        [{"event_id": "model1", "independently_verified": False, "production_recommendations": "DISABLED"}],
        {"status": "HOLD", "accepted": 0, "production_recommendations": "DISABLED"},
        {"independently_verified_settlements": 0, "required_independent_settlements": 300,
         "ready_for_production": False, "production_recommendations": "DISABLED", "blockers": ["NO_RESULTS"]},
    )


class UnifiedEvidenceManifestTests(unittest.TestCase):
    def test_distinct_forecast_types_not_settlements(self):
        data = manifest(*fixtures())
        self.assertEqual(data["four_model_sealed_fixture_count"], 1)
        self.assertEqual(data["poisson_archived_forecast_count"], 1)
        self.assertEqual(data["remaining_independent_settlements"], 300)
        self.assertEqual(data["status"], "HOLD")
        self.assertFalse(data["ready_for_production"])

    def test_mobile_summary_is_hold_and_distinguishes_evidence(self):
        summary = mobile_report(manifest(*fixtures()))
        self.assertIn("四模型已封存賽前場次：1", summary)
        self.assertIn("Poisson 已封存預測場次：1", summary)
        self.assertIn("仍差：300", summary)
        self.assertIn("不可直接相加", summary)
        self.assertIn("正式推薦：未開放", summary)

    def test_mobile_summary_refuses_unsafe_status(self):
        data = manifest(*fixtures())
        data["production_recommendations"] = "ENABLED"
        with self.assertRaises(ValueError):
            mobile_report(data)

    def test_accepted_without_model_forecast_refused(self):
        sealed, model, score, readiness = fixtures()
        score["accepted"] = 1
        with self.assertRaises(ValueError):
            manifest(sealed, [], score, readiness)

    def test_invalid_score_status_refused(self):
        sealed, model, score, readiness = fixtures()
        score["status"] = "PRODUCTION"
        with self.assertRaises(ValueError):
            manifest(sealed, model, score, readiness)

    def test_mobile_report_explains_blockers(self):
        result = mobile_report(manifest(*fixtures()))
        self.assertIn("尚未通過條件：NO_RESULTS", result)
        self.assertIn("研究評分已接納配對：0", result)

    def test_coverage_counts_appear_in_mobile_report(self):
        coverage = {"schema": "football-king-archive-result-coverage-v1",
                    "sealed_forecasts": 1, "matching_result_ids": 0, "missing_result_ids": 1,
                    "independently_attested_settlements": 0,
                    "production_recommendations": "DISABLED"}
        data = manifest(*fixtures(), coverage=coverage)
        summary = mobile_report(data)
        self.assertIn("四模型缺少賽果編號：1", summary)
        self.assertIn("不等於獨立核實", summary)

    def test_mismatched_coverage_fails_closed(self):
        coverage = {"schema": "football-king-archive-result-coverage-v1",
                    "sealed_forecasts": 2, "matching_result_ids": 1, "missing_result_ids": 1,
                    "independently_attested_settlements": 0,
                    "production_recommendations": "DISABLED"}
        with self.assertRaises(ValueError):
            manifest(*fixtures(), coverage=coverage)

    def test_two_source_evidence_appears_in_mobile_summary(self):
        sealed, model, score, readiness = fixtures()
        ft = {"schema": "football-king-two-source-ft-verification-v1",
              "production_recommendations": "DISABLED",
              "external_provenance_rechecked": False,
              "sealed_fixture_count": 1,
              "two_source_verified_count": 0, "verified_records": [],
              "independently_verified": False, "eligible_for_model_scoring": False,
              "observation_consensus_count": 1,
              "observation_records": [{"fixture_id": sealed[0]["fixture_id"],
                                       "status": "AGREED_UNVERIFIED", "result_verified": False,
                                       "independently_verified": False, "eligible_for_model_scoring": False}]}
        report = manifest(sealed, model, score, readiness, ft_evidence=ft)
        self.assertEqual(report["two_source_ft_consensus_count"], 1)
        self.assertIn("雙來源賽果一致性配對：1", mobile_report(report))

    def test_legacy_caller_verified_claim_cannot_enter_manifest(self):
        sealed, model, score, readiness = fixtures()
        ft = {"schema": "football-king-two-source-ft-verification-v1",
              "production_recommendations": "DISABLED", "external_provenance_rechecked": False,
              "sealed_fixture_count": 1, "two_source_verified_count": 1,
              "verified_records": [{"fixture_id": sealed[0]["fixture_id"],
                                    "result_verified": True,
                                    "independent_result_sources": ["OpenFootball", "OpenLigaDB"]}]}
        with self.assertRaises(ValueError):
            manifest(sealed, model, score, readiness, ft_evidence=ft)

    def test_unverified_observation_cannot_carry_true_scoring_flags(self):
        sealed, model, score, readiness = fixtures()
        ft = {"schema": "football-king-two-source-ft-verification-v1",
              "production_recommendations": "DISABLED", "external_provenance_rechecked": False,
              "sealed_fixture_count": 1, "two_source_verified_count": 0, "verified_records": [],
              "independently_verified": False, "eligible_for_model_scoring": False,
              "observation_consensus_count": 1,
              "observation_records": [{"fixture_id": sealed[0]["fixture_id"],
                                       "status": "AGREED_UNVERIFIED", "result_verified": False,
                                       "independently_verified": False, "eligible_for_model_scoring": True}]}
        with self.assertRaises(ValueError):
            manifest(sealed, model, score, readiness, ft_evidence=ft)

    def test_forged_ft_count_fails_closed(self):
        sealed, model, score, readiness = fixtures()
        ft = {"schema": "football-king-two-source-ft-verification-v1",
              "production_recommendations": "DISABLED",
              "external_provenance_rechecked": False,
              "sealed_fixture_count": 1,
              "two_source_verified_count": 1, "verified_records": []}
        with self.assertRaises(ValueError):
            manifest(sealed, model, score, readiness, ft_evidence=ft)

    def test_duplicate_archive_refused(self):
        sealed, model, score, readiness = fixtures()
        with self.assertRaises(ValueError):
            manifest(sealed * 2, model, score, readiness)

    def test_fake_model_verification_refused(self):
        sealed, model, score, readiness = fixtures()
        model[0]["independently_verified"] = True
        with self.assertRaises(ValueError):
            manifest(sealed, model, score, readiness)

    def test_production_promotion_refused(self):
        sealed, model, score, readiness = fixtures()
        readiness["ready_for_production"] = True
        with self.assertRaises(ValueError):
            manifest(sealed, model, score, readiness)


if __name__ == "__main__":
    unittest.main()
