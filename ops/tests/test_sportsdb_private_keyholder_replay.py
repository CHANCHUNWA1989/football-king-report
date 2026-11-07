"""All-synthetic verification of private in-memory replay; real archive key never used."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ops import sportsdb_public_cipher_audit as published
from ops import sportsdb_private_keyholder_replay as keyholder
from ops import sportsdb_result_private_archive as envelope
from ops import private_response_relay as relay
from ops.sportsdb_event_capture import capture
from ops.tests.test_sportsdb_event_capture import original, second
from ops.tests.test_sportsdb_result_private_archive import receipt as http_receipt


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + bytes([0]) + raw).hexdigest()


class KeyholderReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.folder = self.base / published.RUN_DIRECTORY
        self.folder.mkdir()
        self.event_id = "2508372"
        self.ciphertext = b"SYNTHETIC_NOT_REAL_AGE_CIPHERTEXT"
        proof = self.base / "source-private"
        with patch("ops.sportsdb_event_capture._fetch",
                   return_value=(second(), http_receipt(self.event_id))):
            capture(proof, event_id=self.event_id)
        self.raw = (proof / "sportsdb-event.json").read_bytes()
        self.manifest = (proof / "manifest.json").read_bytes()
        self.original = envelope._encode(self.raw, self.manifest)
        self.receipt = {
            "schema": "football-king-sportsdb-age-ciphertext-v1",
            "status": "HOLD", "event_id": self.event_id,
            "encryption": published.ENCRYPTION,
            "original_sha256": hashlib.sha256(self.original).hexdigest(),
            "raw_sha256": hashlib.sha256(self.raw).hexdigest(),
            "recipient_sha256": published.RECIPIENT_SHA,
            "ciphertext_sha256": hashlib.sha256(self.ciphertext).hexdigest(),
            "ciphertext_bytes": len(self.ciphertext),
            "actual_kickoff_authenticated": False,
            "upstream_independence_authenticated": False,
            "independently_verified": False,
            "production_recommendations": "DISABLED",
        }
        (self.folder / (self.event_id + ".age")).write_bytes(self.ciphertext)
        receipt_bytes = (json.dumps(self.receipt, sort_keys=True) + "\n").encode()
        (self.folder / (self.event_id + ".receipt.json")).write_bytes(receipt_bytes)
        self.pins = {
            self.event_id: {
                "ciphertext_sha256": self.receipt["ciphertext_sha256"],
                "ciphertext_bytes": len(self.ciphertext),
                "receipt_git_blob_sha1": git_blob(receipt_bytes),
                "raw_sha256": self.receipt["raw_sha256"],
                "original_sha256": self.receipt["original_sha256"],
            }
        }
        self.fake_identity = b"AGE-SECRET-KEY-PQ-1" + b"A" * 48 + b"\n"

    def replay(self, ciphertext=None):
        with patch.object(published, "EVENTS", self.pins), \
             patch.object(keyholder.relay, "_read", return_value=self.fake_identity), \
             patch.object(keyholder.relay, "_crypto", return_value=(
                 self.original if ciphertext is None else ciphertext)):
            return keyholder.replay(self.folder, event_id=self.event_id,
                                    identity_file=self.base / "fake-identity",
                                    age_binary=self.base / "fake-age")

    def test_in_memory_replay_of_provider_raw_receipt_not_admission(self):
        result = self.replay()
        self.assertTrue(result["private_memory_replay"])
        self.assertEqual(result["decrypted_raw_sha256"], self.receipt["raw_sha256"])
        self.assertEqual(result["provider_event_id"], self.event_id)
        self.assertFalse(result["independently_verified"])
        self.assertFalse(result["publisher_truth_authenticated"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_wrong_or_corrupted_decrypted_pack_rejected(self):
        mutated = self.original[:-1] + bytes([self.original[-1] ^ 1])
        with self.assertRaises(keyholder.DecryptionAuditError) as exc:
            self.replay(mutated)
        self.assertEqual(str(exc.exception), "DECRYPTED_PACK_PIN_MISMATCH")

    def test_valid_sha_but_manifest_not_genuine_live_capture_rejected(self):
        bad = json.loads(self.manifest)
        bad["capture_mode"] = "OFFLINE_TEST_ONLY"
        manifest = (json.dumps(bad, sort_keys=True) + "\n").encode()
        forged = envelope._encode(self.raw, manifest)
        fake_receipt = dict(self.receipt, original_sha256=hashlib.sha256(forged).hexdigest())
        with self.assertRaises(keyholder.DecryptionAuditError) as exc:
            keyholder.decode_original_pack(forged, event_id=self.event_id,
                                           receipt=fake_receipt)
        self.assertEqual(str(exc.exception), "DECRYPTED_SOURCE_RECEIPT_REPLAY_FAILED")

    def test_tampered_ciphertext_rejected_before_private_key_read(self):
        path = self.folder / (self.event_id + ".age")
        path.write_bytes(path.read_bytes() + b"x")
        with patch.object(published, "EVENTS", self.pins), \
             patch.object(keyholder.relay, "_read") as secret_reader, \
             patch.object(keyholder.relay, "_crypto") as decryptor:
            with self.assertRaises(published.PublicEvidenceError):
                keyholder.replay(self.folder, event_id=self.event_id,
                                 identity_file=self.base / "fake-identity",
                                 age_binary=self.base / "fake-age")
            secret_reader.assert_not_called()
            decryptor.assert_not_called()

    def test_unavailable_identity_never_writes_plaintext_or_emits_key(self):
        with patch.object(published, "EVENTS", self.pins):
            with self.assertRaises(keyholder.DecryptionAuditError) as exc:
                keyholder.replay(self.folder, event_id=self.event_id,
                                 identity_file=self.base / "missing",
                                 age_binary=self.base / "unused")
        self.assertEqual(str(exc.exception), "PRIVATE_KEY_OR_PINNED_DECRYPTION_UNAVAILABLE")
        self.assertEqual({f.name for f in self.folder.iterdir()},
                         {self.event_id + ".age", self.event_id + ".receipt.json"})


@unittest.skipUnless(os.environ.get("FOOTBALL_AGE_BINARY") and
                     os.environ.get("FOOTBALL_AGE_KEYGEN"),
                     "Pinned PQ age binaries only in explicit isolated CI job")
class PinnedAgeCryptographicIntegration(unittest.TestCase):
    def test_ephemeral_native_pq_age_encrypt_decrypt_and_replay(self):
        age_bin = Path(os.environ["FOOTBALL_AGE_BINARY"])
        keygen = Path(os.environ["FOOTBALL_AGE_KEYGEN"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = root / "ephemeral-pq-identity"
            # A new disposable test identity, NEVER the actual archive recipient.
            subprocess.run([str(keygen), "-pq", "-o", str(key)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=25)
            os.chmod(key, 0o600)
            result = subprocess.run([str(keygen), "-y", str(key)], check=True,
                                    capture_output=True, timeout=10)
            recipient = result.stdout.decode("ascii").strip()
            self.assertTrue(recipient.startswith("age1pq1"))
            source = root / "synth-proof"
            event_id = "2508371"
            with patch("ops.sportsdb_event_capture._fetch",
                       return_value=(original(), http_receipt(event_id))):
                capture(source, event_id=event_id)
            raw = (source / "sportsdb-event.json").read_bytes()
            manifest = (source / "manifest.json").read_bytes()
            packed = envelope._encode(raw, manifest)
            ciphertext = relay._crypto(
                packed, ["--encrypt", "-r", recipient], age_bin, maximum=650_000)
            archive_dir = root / published.RUN_DIRECTORY
            archive_dir.mkdir()
            receipt = {
                "schema": "football-king-sportsdb-age-ciphertext-v1",
                "status": "HOLD", "event_id": event_id,
                "encryption": published.ENCRYPTION,
                "original_sha256": hashlib.sha256(packed).hexdigest(),
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "recipient_sha256": hashlib.sha256(recipient.encode()).hexdigest(),
                "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
                "ciphertext_bytes": len(ciphertext),
                "actual_kickoff_authenticated": False,
                "upstream_independence_authenticated": False,
                "independently_verified": False,
                "production_recommendations": "DISABLED",
            }
            receipt_bytes = (json.dumps(receipt, sort_keys=True) + "\n").encode()
            (archive_dir / (event_id + ".age")).write_bytes(ciphertext)
            (archive_dir / (event_id + ".receipt.json")).write_bytes(receipt_bytes)
            pins = {event_id: {
                "ciphertext_sha256": receipt["ciphertext_sha256"],
                "ciphertext_bytes": len(ciphertext),
                "receipt_git_blob_sha1": git_blob(receipt_bytes),
                "raw_sha256": receipt["raw_sha256"],
                "original_sha256": receipt["original_sha256"],
            }}
            with patch.object(published, "EVENTS", pins), \
                 patch.object(published, "RECIPIENT_SHA", receipt["recipient_sha256"]):
                actual = keyholder.replay(archive_dir, event_id=event_id,
                                          identity_file=key, age_binary=age_bin)
            self.assertTrue(actual["private_memory_replay"])
            self.assertFalse(actual["independently_verified"])
            self.assertEqual(actual["decrypted_raw_sha256"], receipt["raw_sha256"])
