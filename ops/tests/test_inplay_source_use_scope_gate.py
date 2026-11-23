"""Negative-first synthetic licensing-scope and revocation checks.

No provider API call, contract signing, identity validation, authorization, EV,
or betting recommendation is performed by any of these tests.
"""
import copy
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_source_use_scope_gate import audit_scope_claims
from test_inplay_source_rights_preflight import dossier

NOW = datetime(2026, 11, 23, 8, 25, tzinfo=timezone.utc)


def grants():
    return [
        {
            "provider_claim": "synthetic_alpha",
            "license_holder_claim": "synthetic_operator",
            "rights_record_sha256_unattested": "a" * 64,
            "covered_uses_claim": ["internal_research", "inplay_analytics"],
            "denied_uses_claim": ["redistribution", "betting_recommendations"],
            "territories_claim": ["HK", "GB"],
            "valid_from_utc_claim": "2026-11-01T00:00:00Z",
            "valid_until_utc_claim": "2026-11-30T00:00:00Z",
            "revocation_status_claim": "NO_REVOKE_REPORTED",
        },
        {
            "provider_claim": "synthetic_beta",
            "license_holder_claim": "synthetic_operator",
            "rights_record_sha256_unattested": "b" * 64,
            "covered_uses_claim": ["internal_research", "inplay_analytics"],
            "denied_uses_claim": ["redistribution", "betting_recommendations"],
            "territories_claim": ["HK", "GB"],
            "valid_from_utc_claim": "2026-11-02T00:00:00Z",
            "valid_until_utc_claim": "2026-12-10T00:00:00Z",
            "revocation_status_claim": "NO_REVOKE_REPORTED",
        },
    ]


class SourceUseScopeGateTests(unittest.TestCase):
    def run_gate(self, source_dossier=None, rights=None, *, use="internal_research",
                 territory="HK", holder="synthetic_operator", now=NOW):
        return audit_scope_claims(
            dossier() if source_dossier is None else source_dossier,
            grants() if rights is None else rights,
            requested_use=use, territory=territory,
            license_holder=holder, now=now)

    def check_safe(self, result):
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["source_authorized"])
        self.assertFalse(result["source_data_access_enabled"])
        self.assertFalse(result["provider_identity_authenticated"])
        self.assertFalse(result["signed_grant_verified"])
        self.assertFalse(result["revocation_registry_independently_verified"])
        self.assertFalse(result["eligible_for_model_input"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["certified_forward_samples"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertIsNone(result["recommendation"])

    def test_both_claims_match_scope_but_cannot_authorize(self):
        result=self.run_gate()
        self.check_safe(result)
        self.assertTrue(result["ready_for_external_rights_review"])
        self.assertEqual(result["candidate_grant_count"], 2)
        self.assertEqual(len(result["scope_matrix_sha256_unattested"]),64)

    def test_order_invariant_digest(self):
        normal=self.run_gate()
        flipped=self.run_gate(rights=list(reversed(grants())))
        self.check_safe(flipped)
        self.assertTrue(flipped["ready_for_external_rights_review"])
        self.assertEqual(normal["scope_matrix_sha256_unattested"],
                         flipped["scope_matrix_sha256_unattested"])

    def test_denied_use_must_block_even_if_covered(self):
        proposed=grants()
        proposed[0]["covered_uses_claim"].append("betting_recommendations")
        result=self.run_gate(rights=proposed,use="betting_recommendations")
        self.check_safe(result)
        self.assertFalse(result["ready_for_external_rights_review"])

    def test_not_covered_use_blocks(self):
        self.assertFalse(self.run_gate(use="model_training")["ready_for_external_rights_review"])

    def test_dossier_requested_use_must_match(self):
        source=dossier()
        source["sources"][0]["requested_uses_claim"]=["internal_research"]
        self.assertFalse(self.run_gate(source_dossier=source,
                         use="inplay_analytics")["ready_for_external_rights_review"])

    def test_territory_not_covered_rejects(self):
        self.assertFalse(self.run_gate(territory="US")["ready_for_external_rights_review"])
        for bad in ("hk", "HKG", "HK/GB", None, True, ""):
            self.assertFalse(self.run_gate(territory=bad)["ready_for_external_rights_review"])

    def test_license_holder_mismatch_blocks(self):
        proposed=grants()
        proposed[1]["license_holder_claim"]="another_operator"
        self.assertFalse(self.run_gate(rights=proposed)["ready_for_external_rights_review"])

    def test_expired_or_future_grant_rejects(self):
        for field,value in [
            ("valid_until_utc_claim","2026-11-23T08:25:00Z"),
            ("valid_from_utc_claim","2026-11-24T00:00:00Z"),
        ]:
            proposed=grants()
            proposed[0][field]=value
            self.assertFalse(self.run_gate(rights=proposed)["ready_for_external_rights_review"])

    def test_grant_cannot_exceed_upstream_expiry_claim(self):
        proposed=grants()
        proposed[0]["valid_until_utc_claim"]="2026-12-02T00:00:00Z"
        self.assertFalse(self.run_gate(rights=proposed)["ready_for_external_rights_review"])

    def test_reported_revocation_or_unknown_blocks(self):
        for revoked in ("REVOKED", "UNKNOWN", "", True, None):
            proposed=grants()
            proposed[0]["revocation_status_claim"]=revoked
            self.assertFalse(self.run_gate(rights=proposed)["ready_for_external_rights_review"])

    def test_mismatched_provider_or_contract_digest_blocks(self):
        for field,value in [
            ("provider_claim","other"),
            ("rights_record_sha256_unattested","0"*64),
            ("rights_record_sha256_unattested","a"*63),
        ]:
            proposed=grants()
            proposed[0][field]=value
            self.assertFalse(self.run_gate(rights=proposed)["ready_for_external_rights_review"])

    def test_duplicate_provider_and_unexpected_fields_block(self):
        proposed=grants()
        proposed[1]["provider_claim"]=proposed[0]["provider_claim"]
        self.assertFalse(self.run_gate(rights=proposed)["ready_for_external_rights_review"])
        proposed=grants()
        proposed[0]["source_authorized"]=True
        self.assertFalse(self.run_gate(rights=proposed)["ready_for_external_rights_review"])

    def test_invalid_grant_list_types_duplicates_and_conflicting_scopes_block(self):
        for bad in ([], grants()*2, True, None, "not-list"):
            self.assertFalse(self.run_gate(rights=bad)["ready_for_external_rights_review"])
        proposed=grants()
        proposed[0]["covered_uses_claim"]=["internal_research","internal_research"]
        self.assertFalse(self.run_gate(rights=proposed)["ready_for_external_rights_review"])
        proposed=grants()
        proposed[0]["denied_uses_claim"].append("internal_research")
        self.assertFalse(self.run_gate(rights=proposed)["ready_for_external_rights_review"])

    def test_time_zone_naive_and_invalid_clock_rejected(self):
        self.assertFalse(self.run_gate(now=NOW.replace(tzinfo=None))["ready_for_external_rights_review"])
        proposed=grants()
        proposed[0]["valid_from_utc_claim"]="tomorrow"
        self.assertFalse(self.run_gate(rights=proposed)["ready_for_external_rights_review"])

    def test_public_output_cannot_leak_identity_and_does_not_mutate(self):
        initial=grants()
        original=copy.deepcopy(initial)
        result=self.run_gate(rights=initial)
        self.check_safe(result)
        self.assertEqual(initial,original)
        for secret in ("synthetic_alpha","synthetic_beta","synthetic_operator",
                       "synthetic_fixture_01","alpha.example.org"):
            self.assertNotIn(secret,str(result))


if __name__ == "__main__":
    unittest.main()
