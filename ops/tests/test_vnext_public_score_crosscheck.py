"""Adversarial synthetic checks of researcher-transcribed public score pages.

No HTTP, certified publisher, trusted timestamp or actual prospective forecast.
"""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vnext_public_score_crosscheck import audit_manifest_bytes

REFERENCE = (Path(__file__).resolve().parents[1] / "research_manifests"
             / "openligadb_83156_public_score_crosscheck_20261115.json")


class PublicScoreCrosscheckTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(REFERENCE.read_text())

    def audit(self, payload=None):
        data = self.data if payload is None else payload
        return audit_manifest_bytes(json.dumps(data).encode("utf-8"))

    def test_transcription_agreement_never_promotes_model(self):
        result = self.audit()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"],
                         "PUBLIC_PAGE_SCORE_TRANSCRIPTIONS_AGREE_BUT_UNATTESTED")
        self.assertTrue(result["public_page_transcription_consistent"])
        self.assertEqual(result["source_page_count"], 3)
        for key in ("sources_upstream_independence_authenticated",
                    "source_original_bytes_archived_and_verified",
                    "publisher_identity_independently_authenticated",
                    "capture_timestamp_independently_attested",
                    "result_truth_independently_authenticated",
                    "prematch_forecast_witness_verified",
                    "eligible_for_model_scoring", "positive_ev_verified"):
            self.assertFalse(result[key])
        self.assertEqual(result["certified_prospective_samples"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_score_mismatch(self):
        self.data["source_pages"][2]["score_90m"]["away"] = 2
        self.assertEqual(self.audit()["reason"], "PUBLIC_PAGE_FIXTURE_OR_SCORE_DISAGREEMENT")

    def test_wrong_team(self):
        self.data["source_pages"][0]["away"] = "VfB Stuttgart II"
        self.assertEqual(self.audit()["reason"], "PUBLIC_PAGE_FIXTURE_OR_SCORE_DISAGREEMENT")

    def test_wrong_fixture_date(self):
        self.data["source_pages"][1]["fixture_date"] = "2026-08-29"
        self.assertEqual(self.audit()["reason"], "PUBLIC_PAGE_FIXTURE_OR_SCORE_DISAGREEMENT")

    def test_url_spoof(self):
        self.data["source_pages"][1]["url"] = "https://fcbayern.com.evil.invalid/report"
        self.assertEqual(self.audit()["reason"], "UNPINNED_PUBLIC_SOURCE_URL")

    def test_duplicate_publisher(self):
        self.data["source_pages"][2] = copy.deepcopy(self.data["source_pages"][1])
        self.assertEqual(self.audit()["reason"], "DUPLICATE_OR_UNKNOWN_PUBLIC_PUBLISHER")

    def test_fake_source_signature(self):
        self.data["publisher_signed_capture"] = True
        self.assertEqual(self.audit()["reason"], "SELF_CERTIFICATION_NOT_ALLOWED")

    def test_fake_independence(self):
        self.data["upstream_independence_audited"] = True
        self.assertEqual(self.audit()["reason"], "SELF_CERTIFICATION_NOT_ALLOWED")

    def test_fake_scoring_approval(self):
        self.data["future_model_scoring_authorized"] = True
        self.assertEqual(self.audit()["reason"], "SELF_CERTIFICATION_NOT_ALLOWED")

    def test_altered_original_digest(self):
        self.data["openligadb_observed_sha256_unattested"] = "a" * 64
        self.assertEqual(self.audit()["reason"],
                         "PUBLIC_CROSSCHECK_FIXTURE_OR_DIGEST_CONFLICT")

    def test_self_certification_extra_field(self):
        self.data["result_certified"] = True
        self.assertEqual(self.audit()["reason"], "UNEXPECTED_PUBLIC_CROSSCHECK_SCHEMA")

    def test_duplicate_keys(self):
        self.assertEqual(audit_manifest_bytes(
            b'{"schema":"a","schema":"b"}')["reason"], "DUPLICATE_MANIFEST_KEY")

    def test_nan(self):
        self.data["score_90m"]["home"] = float("nan")
        self.assertEqual(self.audit()["reason"], "NONFINITE_MANIFEST_NUMBER")

    def test_oversize(self):
        self.assertEqual(audit_manifest_bytes(
            b"x" * 20000)["reason"], "INVALID_PUBLIC_CROSSCHECK_MANIFEST_SIZE")

    def test_wrong_fixture_id(self):
        self.data["fixture_id"] = "OpenLigaDB:99999"
        self.assertEqual(self.audit()["reason"],
                         "PUBLIC_CROSSCHECK_FIXTURE_OR_DIGEST_CONFLICT")


if __name__ == "__main__":
    unittest.main()
