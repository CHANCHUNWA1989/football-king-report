"""PR-07 fixed provider policy and case-level proof linkage tests.

Any 'good' witness in this suite is mocked gh verification output, NOT a
real Sigstore/Rekor event. All final-score links remain HOLD by design.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.tests.test_vnext_forecast_attestation_gate import WitnessFixture
from vnext_fixture_evidence_link import audit_source_access, link_fixture

SCOPE = "bundesliga/2026-2027/regulation-90-minutes"


def result():
    return {
        "fixture_id": "fixture-pr07-001",
        "kickoff_utc": "2026-08-01T20:00:00Z",
        "home_goals": 2, "away_goals": 1,
        "result_received_utc": "2026-08-01T23:00:00Z",
        "source_raw_sha256": "e" * 64,
        "result_independently_authenticated": False,
    }


def observations():
    return [{
        "provider": prov,
        "fixture_id": "fixture-pr07-001",
        "provider_fixture_id": "prov-match-" + prov,
        "source_scope": SCOPE,
        "home_goals": 2, "away_goals": 1,
        "source_updated_utc": "2026-08-01T22:00:00Z",
        "received_utc": "2026-08-01T22:01:00Z",
        "raw_sha256": "f" * 64,
    } for prov in ("NDR", "OpenLigaDB")]


class RightsAndEvidenceLinkTests(WitnessFixture):
    def link(self, res=None, obs=None, *, mocked_gh=True):
        kwargs = dict(self.kwargs)
        kwargs["checked_utc"] = "2026-08-02T00:00:00Z"
        if mocked_gh:
            with self._mocked():
                return link_fixture(
                    self.root, self.seal["file_name"], **kwargs,
                    result_record=result() if res is None else res,
                    result_observations=observations() if obs is None else obs)
        return link_fixture(
            self.root, self.seal["file_name"], **kwargs,
            result_record=result() if res is None else res,
            result_observations=observations() if obs is None else obs)

    def test_mocked_signed_forecast_plus_agreeing_sources_remains_hold(self):
        report = self.link()
        self.assertEqual(report["status"], "HOLD")
        self.assertTrue(report["forecast_external_byte_time_verified"])
        self.assertTrue(report["observation_agreement"])
        self.assertEqual(report["reason"],
                         "WITNESSED_FORECAST_BUT_RESULT_RIGHTS_AND_INDEPENDENCE_UNVERIFIED")
        self.assertEqual(report["fixture_id"], "fixture-pr07-001")
        self.assertEqual(report["forecast_sha256"], self.seal["content_sha256"])
        self.assertEqual(len(report["provider_references"]), 2)
        self.assertEqual(len(report["forecast_source_references"]), 1)
        for key in ("source_access_authorized", "publisher_independence_authenticated",
                    "result_truth_verified", "actual_kickoff_verified",
                    "eligible_for_model_scoring", "eligible_for_betting",
                    "positive_ev_verified"):
            self.assertFalse(report[key])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_pinned_policy_always_refuses_unproven_access(self):
        for provider in ("NDR", "DFB", "OpenFootball", "OpenLigaDB"):
            with self.subTest(provider=provider):
                for operation in ("AUTOMATED_COLLECTION", "DERIVED_METADATA", "PUBLIC_RAW_REUSE"):
                    report = audit_source_access(provider, scope=SCOPE, operation=operation)
                    self.assertEqual(report["status"], "HOLD")
                    self.assertFalse(report["source_access_authorized"])
                    self.assertEqual(report["upstream_relationship"], "UNKNOWN")

    def test_dfb_automated_crawl_is_explicitly_denied(self):
        r = audit_source_access("DFB", scope=SCOPE, operation="AUTOMATED_COLLECTION")
        self.assertEqual(r["reason"],
                         "DFB_AUTOMATED_COLLECTION_AND_PUBLIC_RAW_REUSE_NOT_AUTHORIZED")

    def test_false_scope_or_new_provider_has_no_rights(self):
        for prov, scope, op in (
            ("DFB", "ucl/2026-2027/regulation-90-minutes", "DERIVED_METADATA"),
            ("UnknownData", SCOPE, "AUTOMATED_COLLECTION"),
            ("NDR", SCOPE, "BUY_LICENSE_AUTOMATICALLY"),
        ):
            with self.subTest(provider=prov):
                report = audit_source_access(prov, scope=scope, operation=op)
                self.assertEqual(report["status"], "HOLD")
                self.assertFalse(report["source_access_authorized"])

    def test_unsigned_forecast_never_enters_case_linkage(self):
        with self._mocked(status=1):
            report = self.link(mocked_gh=False)
        self.assertEqual(report["reason"], "FORECAST_WITNESS_NOT_AUTHENTICATED")

    def test_wrong_fixture_join_rejected(self):
        item = result()
        item["fixture_id"] = "another-match"
        self.assertEqual(self.link(res=item)["reason"],
                         "RESULT_IDENTITY_OR_CERTIFICATION_CONFLICT")

    def test_recorded_kickoff_conflict_must_not_get_promoted(self):
        item = result()
        item["kickoff_utc"] = "2026-08-02T20:00:00Z"
        # Extra independent kickoff field is not meaningful evidence; strictly
        # disallow caller-supplied mismatched metadata from masquerading as proof.
        self.assertEqual(self.link(res=item)["reason"],
                         "RESULT_IDENTITY_OR_CERTIFICATION_CONFLICT")

    def test_result_cannot_precede_regulation_end(self):
        item = result()
        item["result_received_utc"] = "2026-08-01T20:40:00Z"
        self.assertEqual(self.link(res=item)["reason"],
                         "RESULT_BEFORE_REGULATION_COMPLETION")

    def test_conflicting_sources_not_promoted(self):
        obs = observations()
        obs[1]["away_goals"] = 4
        self.assertEqual(self.link(obs=obs)["reason"],
                         "RESULT_SOURCES_DISAGREE_OR_OUTSIDE_POLICY")

    def test_two_source_agreement_not_enough_when_result_mismatches(self):
        item = result()
        item["home_goals"] = 3
        self.assertEqual(self.link(res=item)["reason"],
                         "RESULT_NOT_SUPPORTED_BY_OBSERVATIONS")

    def test_duplicate_upstream_provider_cannot_count_twice(self):
        obs = observations()
        obs[1]["provider"] = "NDR"
        self.assertEqual(self.link(obs=obs)["reason"],
                         "RESULT_SOURCES_DISAGREE_OR_OUTSIDE_POLICY")

    def test_fake_result_license_certificate_flag_rejected(self):
        item = result()
        item["result_independently_authenticated"] = True
        self.assertEqual(self.link(res=item)["status"], "HOLD")
        obs = observations()
        obs[0]["license_granted"] = True
        self.assertEqual(self.link(obs=obs)["status"], "HOLD")

    def test_results_from_later_decision_time_are_not_accepted(self):
        obs = observations()
        obs[0]["received_utc"] = "2026-08-02T01:00:00Z"
        self.assertEqual(self.link(obs=obs)["reason"],
                         "RESULT_SOURCES_DISAGREE_OR_OUTSIDE_POLICY")

    def test_bookmaker_or_ev_cannot_be_injected(self):
        item = result()
        item["market_odds"] = 2.3
        report = self.link(res=item)
        self.assertEqual(report["status"], "HOLD")
        self.assertFalse(report["positive_ev_verified"])

    def test_missing_bundle_fails_closed(self):
        kwargs = dict(self.kwargs)
        kwargs["bundle_path"] = self.root / "missing.bundle"
        kwargs["checked_utc"] = "2026-08-02T00:00:00Z"
        with self._mocked():
            report = link_fixture(self.root, self.seal["file_name"], **kwargs,
                                  result_record=result(), result_observations=observations())
        self.assertEqual(report["reason"], "FORECAST_WITNESS_NOT_AUTHENTICATED")


if __name__ == "__main__":
    unittest.main()
