"""Synthetic-only checks for external source onboarding preflight.

Passing these checks NEVER verifies licensing, origin, signatures, live access
or provider independence. No network or real provider contracts are used.
"""
import copy
from datetime import datetime, timezone, timedelta
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_source_rights_preflight import assess_source_readiness

NOW = datetime(2026, 11, 23, 8, 20, tzinfo=timezone.utc)


def dossier():
    return {
        "schema": "football-king-inplay-source-rights-preflight-v1",
        "fixture_id_claim": "synthetic_fixture_01",
        "decision_utc_claim": "2026-11-23T08:15:00Z",
        "private_inventory_sha256_unattested": "f" * 64,
        "sources": [
            {
                "provider_claim": "synthetic_alpha",
                "api_host_claim": "alpha.example.org",
                "rights_record_sha256_unattested": "a" * 64,
                "capture_receipt_sha256_unattested": "c" * 64,
                "rights_expiry_utc_claim": "2026-12-01T00:00:00Z",
                "requested_uses_claim": ["internal_research", "inplay_analytics"],
            },
            {
                "provider_claim": "synthetic_beta",
                "api_host_claim": "beta.example.org",
                "rights_record_sha256_unattested": "b" * 64,
                "capture_receipt_sha256_unattested": "d" * 64,
                "rights_expiry_utc_claim": "2026-12-15T00:00:00Z",
                "requested_uses_claim": ["internal_research", "inplay_analytics"],
            },
        ],
    }


class SourceRightsPreflightTests(unittest.TestCase):
    def check_hold(self, obj, now=NOW):
        result = assess_source_readiness(obj, now=now)
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["source_authorized"])
        self.assertFalse(result["source_data_access_enabled"])
        self.assertFalse(result["provider_identity_authenticated"])
        self.assertFalse(result["source_independence_verified"])
        self.assertFalse(result["third_party_timestamp_verified"])
        self.assertFalse(result["eligible_for_model_input"])
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["certified_forward_samples"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertIsNone(result["recommendation"])
        return result

    def test_complete_self_claims_only_ready_for_human_review(self):
        result = self.check_hold(dossier())
        self.assertTrue(result["ready_for_independent_review"])
        self.assertEqual(result["candidate_source_count"], 2)
        self.assertEqual(result["reason"], "EXTERNAL_LICENSE_AND_PROVENANCE_REVIEW_REQUIRED")
        self.assertEqual(len(result["preflight_sha256_unattested"]), 64)

    def test_input_order_is_not_material_to_self_hash(self):
        original = dossier()
        swapped = dossier()
        swapped["sources"].reverse()
        a, b = self.check_hold(original), self.check_hold(swapped)
        self.assertEqual(a["preflight_sha256_unattested"], b["preflight_sha256_unattested"])

    def test_unauthorized_authorization_shortcut_is_rejected(self):
        obj = dossier()
        obj["source_authorized"] = True
        result = self.check_hold(obj)
        self.assertFalse(result["ready_for_independent_review"])
        obj = dossier()
        obj["sources"][0]["approved"] = True
        result = self.check_hold(obj)
        self.assertFalse(result["ready_for_independent_review"])

    def test_missing_or_extra_required_data_is_rejected(self):
        obj = dossier()
        del obj["private_inventory_sha256_unattested"]
        self.assertFalse(self.check_hold(obj)["ready_for_independent_review"])
        obj = dossier()
        del obj["sources"][0]["rights_record_sha256_unattested"]
        self.assertFalse(self.check_hold(obj)["ready_for_independent_review"])

    def test_invalid_or_untrusted_digests_rejected(self):
        for bad in ("0"*63, "Z"*64, "A"*64, "../path", True, None, "x"*4096):
            obj = dossier()
            obj["sources"][0]["rights_record_sha256_unattested"] = bad
            self.assertFalse(self.check_hold(obj)["ready_for_independent_review"])
        obj = dossier()
        obj["private_inventory_sha256_unattested"] = "0"*63
        self.assertFalse(self.check_hold(obj)["ready_for_independent_review"])

    def test_same_provider_host_or_receipt_conflicts_rejected(self):
        for field in ("provider_claim", "api_host_claim",
                      "capture_receipt_sha256_unattested"):
            obj = dossier()
            obj["sources"][1][field] = obj["sources"][0][field]
            self.assertFalse(self.check_hold(obj)["ready_for_independent_review"])

    def test_host_shape_rejects_urls_private_names_and_spoofs(self):
        for bad in ("https://alpha.example.org/p?key=SECRET",
                    "alpha.example.org:443", "alpha.example.org@evil.tld",
                    "127.0.0.1", "localhost", "data.local", "EXAMPLE.ORG",
                    "alpha.example.org/", "alpha..example.org",
                    "alpha.example.org#secret", "alpha_internal.example.org"):
            obj = dossier()
            obj["sources"][0]["api_host_claim"] = bad
            self.assertFalse(self.check_hold(obj)["ready_for_independent_review"])

    def test_expired_or_equal_to_current_license_claim_rejected(self):
        for end in ("2026-11-22T00:00:00Z", "2026-11-23T08:20:00Z"):
            obj = dossier()
            obj["sources"][0]["rights_expiry_utc_claim"] = end
            self.assertFalse(self.check_hold(obj)["ready_for_independent_review"])

    def test_future_decision_rejected(self):
        obj = dossier()
        obj["decision_utc_claim"] = "2026-11-24T08:20:00Z"
        self.assertFalse(self.check_hold(obj)["ready_for_independent_review"])

    def test_invalid_requested_use_and_duplicate_scope_rejected(self):
        for uses in ([], ["internal_research", "internal_research"],
                     ["betting_profits"], [True], "internal_research",
                     ["internal_research"] * 40):
            obj = dossier()
            obj["sources"][0]["requested_uses_claim"] = uses
            self.assertFalse(self.check_hold(obj)["ready_for_independent_review"])

    def test_requested_betting_scope_cannot_enable_predictions(self):
        obj = dossier()
        obj["sources"][0]["requested_uses_claim"] = ["betting_recommendations"]
        obj["sources"][1]["requested_uses_claim"] = ["betting_recommendations"]
        result = self.check_hold(obj)
        self.assertTrue(result["ready_for_independent_review"])

    def test_naive_clock_or_malformed_time_rejected(self):
        obj = dossier()
        self.assertFalse(self.check_hold(obj, NOW.replace(tzinfo=None))["ready_for_independent_review"])
        obj["decision_utc_claim"] = "tomorrow"
        self.assertFalse(self.check_hold(obj)["ready_for_independent_review"])

    def test_private_claims_or_secrets_never_echoed(self):
        obj = dossier()
        obj["sources"][0]["provider_claim"] = "synthetic_credential_DO_NOT_LOG"
        report = self.check_hold(obj)
        self.assertNotIn("synthetic_credential_DO_NOT_LOG", str(report))
        self.assertNotIn("alpha.example.org", str(report))
        self.assertNotIn("synthetic_fixture_01", str(report))

    def test_input_not_mutated(self):
        obj = dossier()
        before = copy.deepcopy(obj)
        self.check_hold(obj)
        self.assertEqual(obj, before)

    def test_wrong_source_count_and_types_rejected(self):
        for bad in ([], [dossier()["sources"][0]],
                    dossier()["sources"] * 2, None, "a string", True):
            obj = dossier()
            obj["sources"] = bad
            self.assertFalse(self.check_hold(obj)["ready_for_independent_review"])


if __name__ == "__main__":
    unittest.main()
