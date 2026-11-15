"""Tests for zero-secret public candidate matching (never FT certification)."""
import copy
import json
from pathlib import Path
import unittest

from ops.public_result_candidate_join import audit, CANDIDATES

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "evidence/settled.json"
RECEIPT_ROOT = ROOT / "evidence/encrypted_result_sources/v1/42406458039-1"


def fixtures():
    with ARCHIVE.open(encoding="utf-8") as fh:
        ledger = json.load(fh)
    receipts = {event: json.loads((RECEIPT_ROOT / (event + ".receipt.json"))
                                   .read_text(encoding="utf-8"))
                for event in CANDIDATES}
    return ledger["samples"], receipts


class PublicResultCandidateJoinTests(unittest.TestCase):
    def test_two_real_public_receipt_metadata_matches_remain_held(self):
        records, receipts = fixtures()
        result = audit(records, receipts)
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["certified_case_count"], 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["independently_verified"])
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertFalse(result["public_source_content_authenticated_by_ci"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(set(x["event_id"] for x in result["candidate_matches"]),
                         {"2508371", "2508372"})
        self.assertTrue(all(not x["native_fixture_id_authenticated"]
                            for x in result["candidate_matches"]))

    def test_wrong_ledger_outcome_or_timestamp_not_joined(self):
        records, receipts = fixtures()
        for item in records:
            if item["key"] == CANDIDATES["2508371"]["key"]:
                item["y"] = 0
                break
        result = audit(records, receipts)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["certified_case_count"], 0)
        records, receipts = fixtures()
        for item in records:
            if item["key"] == CANDIDATES["2508372"]["key"]:
                item["forecast_utc"] = item["kickoff_utc"]
                break
        self.assertEqual(audit(records, receipts)["candidate_count"], 1)

    def test_duplicate_key_quarantined_not_first_row_wins(self):
        records, receipts = fixtures()
        row = next(item for item in records if item["key"] == CANDIDATES["2508371"]["key"])
        records.append(copy.deepcopy(row))
        report = audit(records, receipts)
        self.assertEqual(report["candidate_count"], 1)
        self.assertIn("2508371", report["quarantined_event_ids"])
        self.assertEqual(report["certified_case_count"], 0)

    def test_forged_receipt_certification_rejected(self):
        records, receipts = fixtures()
        receipts["2508371"]["independently_verified"] = True
        report = audit(records, receipts)
        self.assertEqual(report["candidate_count"], 1)
        self.assertIn("2508371", report["quarantined_event_ids"])
        self.assertEqual(report["certified_case_count"], 0)

    def test_malformed_inputs_fail_closed(self):
        records, receipts = fixtures()
        for invalid in (None, {}, "fake", records * 20):
            with self.subTest(invalid=str(type(invalid))):
                with self.assertRaises(ValueError):
                    audit(invalid, receipts)
        with self.assertRaises(ValueError):
            audit(records, "untrusted")
        with self.assertRaises(ValueError):
            audit(records, {"2508371": receipts["2508371"]})

    def test_legacy_fixture_keys_do_not_authenticate_native_event_id(self):
        records, receipts = fixtures()
        result = audit(records, receipts)
        for item in result["candidate_matches"]:
            self.assertEqual(item["source_match_quality"], "CLAIMED_NAME_TIME_SCORE_ONLY")
            self.assertFalse(item["encrypted_original_plaintext_verified"])
            self.assertFalse(item["second_upstream_independence_verified"])
            self.assertFalse(item["official_actual_kickoff_verified"])
            self.assertFalse(item["forward_forecast_bytes_authenticated"])
            self.assertFalse(item["positive_ev_verified"])
            self.assertFalse(item["eligible_for_model_scoring"])


    def test_receipt_digest_tamper_rejected_even_if_sha256_syntax_valid(self):
        # Previously _receipt_safe() accepted ANY 64-hex digest, which
        # allowed a visibly altered receipt to be counted as a candidate.
        fields = ("raw_sha256", "original_sha256", "ciphertext_sha256",
                  "recipient_sha256")
        for field in fields:
            records, receipts = fixtures()
            receipts["2508371"][field] = "f" * 64
            with self.subTest(field=field):
                result = audit(records, receipts)
                self.assertEqual(result["candidate_count"], 1)
                self.assertIn("2508371", result["quarantined_event_ids"])
                self.assertEqual(result["certified_case_count"], 0)
                self.assertFalse(result["eligible_for_model_scoring"])

    def test_receipt_byte_length_tamper_rejected(self):
        records, receipts = fixtures()
        receipts["2508372"]["ciphertext_bytes"] += 1
        report = audit(records, receipts)
        self.assertEqual(report["candidate_count"], 1)
        self.assertIn("2508372", report["quarantined_event_ids"])
        self.assertEqual(report["certified_case_count"], 0)

    def test_unaltered_public_pins_do_not_certify_under_any_scenario(self):
        records, receipts = fixtures()
        report = audit(records, receipts)
        self.assertEqual(report["candidate_count"], 2)
        self.assertEqual(report["certified_case_count"], 0)
        self.assertFalse(report["public_receipt_integrity_cryptographically_verified_here"])

    def test_archived_1x2_label_does_not_claim_exact_ft_score_verified(self):
        # The archived settled.json contains only y=0/1/2, not [home, away].
        # Existing quality text said "SCORE_ONLY", misleadingly suggesting
        # exact final score was checked in both records.
        rows, receipts = fixtures()
        result = audit(rows, receipts)
        self.assertEqual(result["candidate_count"], 2)
        for item in result["candidate_matches"]:
            self.assertEqual(item["source_match_quality"],
                             "CLAIMED_NAME_TIME_1X2_LABEL_ONLY")
            self.assertTrue(item["archived_result_1x2_label_only"])
            self.assertFalse(item["archived_exact_score_verified"])
            self.assertIn("public_ft_score_claim_unverified", item)
            self.assertNotIn("score_ft_public_claim", item)
            self.assertFalse(item["eligible_for_model_scoring"])
        self.assertFalse(result["any_archived_exact_score_verified"])

    def test_explicit_conflicting_archived_ft_score_is_quarantined(self):
        # A corrupted/new record with a conflicting FT score must never
        # count as a matched candidate just because the 1X2 label matches.
        rows, receipts = fixtures()
        target = next(row for row in rows
                      if row["key"] == CANDIDATES["2508371"]["key"])
        target["score_ft"] = [1, 1]  # draw label still matches, FT does not
        result = audit(rows, receipts)
        self.assertEqual(result["candidate_count"], 1)
        self.assertIn("2508371", result["quarantined_event_ids"])
        self.assertEqual(result["certified_case_count"], 0)


if __name__ == "__main__":
    unittest.main()
