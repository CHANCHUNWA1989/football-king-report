"""No-key synthetic tests of the native-age encrypted-result wrapper."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ops.sportsdb_encrypted_result_archive import encrypt, EncryptionError
from ops.sportsdb_event_capture import capture
from ops.tests.test_sportsdb_event_capture import original, second
from ops.tests.test_sportsdb_result_private_archive import receipt


class ResultEncryptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.out = self.base / "ciphertext"
        self.out.mkdir(mode=0o700)
        os.chmod(self.out, 0o700)
        self.recipient = (Path(__file__).resolve().parents[2]
                          / "sources/policies/private_original_recipient_v1.txt")

    def make_proof(self, event_id):
        folder = self.base / event_id
        raw = original() if event_id == "2508371" else second()
        with patch("ops.sportsdb_event_capture._fetch",
                   return_value=(raw, receipt(event_id))):
            capture(folder, event_id=event_id)
        return folder, raw

    def test_encryption_outputs_only_ciphertext_and_safe_pins(self):
        for event_id in ("2508371", "2508372"):
            with self.subTest(event_id=event_id):
                proof, raw = self.make_proof(event_id)
                cipher = b"age-encrypted-synthetic-" + event_id.encode()
                with patch("ops.sportsdb_encrypted_result_archive.relay._crypto",
                           return_value=cipher):
                    report = encrypt(proof, self.out, event_id=event_id,
                                     age_binary=self.base / "unused-age",
                                     recipient_file=self.recipient)
                self.assertEqual((self.out / (event_id + ".age")).read_bytes(), cipher)
                self.assertNotIn(raw, cipher)
                self.assertEqual(report["ciphertext_sha256"],
                                 hashlib.sha256(cipher).hexdigest())
                self.assertFalse(report["independently_verified"])
                self.assertEqual(report["production_recommendations"], "DISABLED")
                self.assertFalse(report["upstream_independence_authenticated"])
                self.assertEqual(json.loads(
                    (self.out / (event_id + ".receipt.json")).read_text()), report)
                self.assertEqual(os.stat(self.out / (event_id + ".age")).st_mode & 0o777, 0o600)

    def test_offline_fake_source_cannot_be_packaged_as_live(self):
        folder = self.base / "offline"
        capture(folder, raw=original())
        with patch("ops.sportsdb_encrypted_result_archive.relay._crypto") as crypto:
            with self.assertRaises(Exception):
                encrypt(folder, self.out, event_id="2508371",
                        age_binary=self.base / "unused-age",
                        recipient_file=self.recipient)
            crypto.assert_not_called()

    def test_invalid_event_refused_before_ciphertext(self):
        with self.assertRaises(EncryptionError) as cm:
            encrypt(self.base / "nothing", self.out, event_id="2508373",
                    age_binary=self.base / "unused-age",
                    recipient_file=self.recipient)
        self.assertEqual(str(cm.exception), "UNSUPPORTED_RESULT_EVENT")

    def test_failed_crypto_cannot_publish_raw(self):
        proof, _ = self.make_proof("2508371")
        with patch("ops.sportsdb_encrypted_result_archive.relay._crypto",
                   side_effect=RuntimeError("synthetic_crypto_failure")):
            with self.assertRaises(EncryptionError) as cm:
                encrypt(proof, self.out, event_id="2508371",
                        age_binary=self.base / "unused-age",
                        recipient_file=self.recipient)
        self.assertEqual(str(cm.exception), "PINNED_ENCRYPTION_UNAVAILABLE")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_existing_ciphertext_not_overwritten(self):
        proof, _ = self.make_proof("2508371")
        existing = self.out / "2508371.age"
        existing.write_bytes(b"do-not-replace")
        with patch("ops.sportsdb_encrypted_result_archive.relay._crypto",
                   return_value=b"fake-ciphertext"):
            with self.assertRaises(EncryptionError):
                encrypt(proof, self.out, event_id="2508371",
                        age_binary=self.base / "unused-age",
                        recipient_file=self.recipient)
        self.assertEqual(existing.read_bytes(), b"do-not-replace")


if __name__ == "__main__":
    unittest.main()
