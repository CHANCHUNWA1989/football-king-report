"""Synthetic negative tests for the read-only published ciphertext audit.

No private identity, external API, or actual outcome is used here.
"""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ops import sportsdb_public_cipher_audit as verifier


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + bytes([0]) + raw).hexdigest()


class PublicCipherAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / verifier.RUN_DIRECTORY
        self.folder.mkdir()
        self.pins = {}
        for event_id in ("2508371", "2508372"):
            cipher = b"synthetic-ciphertext-do-not-decrypt-" + event_id.encode()
            original = hashlib.sha256(("original:" + event_id).encode()).hexdigest()
            raw = hashlib.sha256(("raw:" + event_id).encode()).hexdigest()
            receipt = {
                "schema": "football-king-sportsdb-age-ciphertext-v1",
                "status": "HOLD",
                "event_id": event_id,
                "encryption": verifier.ENCRYPTION,
                "original_sha256": original,
                "raw_sha256": raw,
                "recipient_sha256": verifier.RECIPIENT_SHA,
                "ciphertext_sha256": hashlib.sha256(cipher).hexdigest(),
                "ciphertext_bytes": len(cipher),
                "actual_kickoff_authenticated": False,
                "upstream_independence_authenticated": False,
                "independently_verified": False,
                "production_recommendations": "DISABLED",
            }
            data = (json.dumps(receipt, sort_keys=True) + "\n").encode()
            (self.folder / (event_id + ".age")).write_bytes(cipher)
            (self.folder / (event_id + ".receipt.json")).write_bytes(data)
            self.pins[event_id] = {
                "ciphertext_sha256": hashlib.sha256(cipher).hexdigest(),
                "ciphertext_bytes": len(cipher),
                "raw_sha256": raw, "original_sha256": original,
                "receipt_git_blob_sha1": blob(data),
            }

    def run_audit(self):
        with patch.object(verifier, "EVENTS", self.pins):
            return verifier.audit(self.folder)

    def test_both_ciphertexts_and_receipts_check_without_keys(self):
        report = self.run_audit()
        self.assertTrue(report["ciphertext_integrity_verified"])
        self.assertTrue(report["receipt_pins_verified"])
        self.assertFalse(report["raw_post_decryption_replay_verified"])
        self.assertEqual(report["certified_case_count"], 0)
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(len(report["checks"]), 2)
        self.assertFalse(any(x["independently_verified"] for x in report["checks"]))

    def test_single_byte_ciphertext_tamper_rejected(self):
        file = self.folder / "2508372.age"
        value = file.read_bytes()
        file.write_bytes(value[:-1] + bytes([value[-1] ^ 1]))
        with self.assertRaises(verifier.PublicEvidenceError) as cm:
            self.run_audit()
        self.assertEqual(str(cm.exception), "CIPHERTEXT_PIN_MISMATCH")

    def test_pinned_receipt_byte_change_rejected(self):
        file = self.folder / "2508371.receipt.json"
        file.write_bytes(file.read_bytes() + b" ")
        with self.assertRaises(verifier.PublicEvidenceError) as cm:
            self.run_audit()
        self.assertEqual(str(cm.exception), "RECEIPT_ORIGINAL_BYTES_CHANGED")

    def test_claim_to_certify_rejected(self):
        file = self.folder / "2508371.receipt.json"
        report = json.loads(file.read_text())
        report["independently_verified"] = True
        file.write_text(json.dumps(report))
        with self.assertRaises(verifier.PublicEvidenceError):
            self.run_audit()

    def test_duplicate_json_key_rejected(self):
        file = self.folder / "2508372.receipt.json"
        data = file.read_bytes().rstrip()
        file.write_bytes(data[:-1] + b', "status":"HOLD"}')
        with self.assertRaises(verifier.PublicEvidenceError) as cm:
            self.run_audit()
        self.assertEqual(str(cm.exception), "DUPLICATE_RECEIPT_KEY")

    def test_symlink_in_place_of_ciphertext_rejected(self):
        file = self.folder / "2508371.age"
        target = self.folder / "2508372.age"
        file.unlink()
        file.symlink_to(target)
        with self.assertRaises(verifier.PublicEvidenceError) as cm:
            self.run_audit()
        self.assertEqual(str(cm.exception), "UNSAFE_EVIDENCE_FILE")

    def test_extra_file_and_missing_file_rejected(self):
        extra = self.folder / "untrusted.txt"
        extra.write_text("synthetic")
        with self.assertRaises(verifier.PublicEvidenceError) as cm:
            self.run_audit()
        self.assertEqual(str(cm.exception), "UNEXPECTED_EVIDENCE_FILES")
        extra.unlink()
        (self.folder / "2508372.age").unlink()
        with self.assertRaises(verifier.PublicEvidenceError) as cm:
            self.run_audit()
        self.assertEqual(str(cm.exception), "UNEXPECTED_EVIDENCE_FILES")

    def test_wrong_run_directory_refused(self):
        other = self.folder.parent / "untrusted-run"
        self.folder.rename(other)
        with self.assertRaises(verifier.PublicEvidenceError) as cm:
            with patch.object(verifier, "EVENTS", self.pins):
                verifier.audit(other)
        self.assertEqual(str(cm.exception), "UNSAFE_EVIDENCE_DIRECTORY")

    def test_cannot_confuse_another_event_receipt(self):
        a = self.folder / "2508371.receipt.json"
        b = self.folder / "2508372.receipt.json"
        data_a, data_b = a.read_bytes(), b.read_bytes()
        a.write_bytes(data_b)
        b.write_bytes(data_a)
        with self.assertRaises(verifier.PublicEvidenceError):
            self.run_audit()


if __name__ == "__main__":
    unittest.main()
