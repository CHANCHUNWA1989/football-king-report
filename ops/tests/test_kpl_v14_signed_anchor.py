"""Synthetic-only KPL V14 Ed25519 vectors: ephemeral test key, never commit private keys."""
import base64
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops.tests.test_kpl_v12_anchor_qualification import make_archive
from research.kpl_v14_signed_anchor import (
    build_unsigned_anchor_payload, verify_signed_anchor_receipt,
    audit_signed_anchor_batch, canonical_signed_message)


class V14Ed25519Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls._priv = Path(cls._tmp.name) / "test-only-private.pem"
        public = Path(cls._tmp.name) / "test-only-public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "Ed25519",
                        "-out", str(cls._priv)], capture_output=True, check=True)
        subprocess.run(["openssl", "pkey", "-in", str(cls._priv), "-pubout",
                        "-out", str(public)], capture_output=True, check=True)
        cls.pub = public.read_text(encoding="ascii")
        der = subprocess.run(["openssl", "pkey", "-pubin", "-inform", "PEM",
                              "-outform", "DER"], input=cls.pub.encode(),
                             capture_output=True, check=True).stdout
        cls.pin = hashlib.sha256(der).hexdigest()
        cls.trusted = {"synthetic-witness": {"public_key_pem": cls.pub,
                                            "spki_sha256": cls.pin}}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def sign(self, payload, *, key_id="synthetic-witness"):
        with tempfile.TemporaryDirectory() as d:
            message = Path(d) / "message"
            signature = Path(d) / "signature"
            message.write_bytes(canonical_signed_message(payload))
            subprocess.run(["openssl", "pkeyutl", "-sign", "-rawin",
                            "-inkey", str(self._priv), "-in", str(message),
                            "-out", str(signature)], capture_output=True, check=True)
            return {"payload": copy.deepcopy(payload), "key_id": key_id,
                    "signature_b64": base64.b64encode(signature.read_bytes()).decode("ascii")}

    def signed_for(self, path, index, *, nonce=None):
        from datetime import datetime, timedelta
        from research.kpl_v13_archive_snapshot import read_verified_archive_snapshot
        row = read_verified_archive_snapshot(path)["entries"][index-1]["forecast"]
        observed = datetime.fromisoformat(row["forecast_at"].replace("Z", "+00:00"))
        payload = build_unsigned_anchor_payload(
            path, index, witnessed_at=(observed + timedelta(minutes=1)).isoformat(),
            nonce=nonce or f"synthetic-unique-nonce-{index:03d}")
        return self.sign(payload)

    def test_pinned_crypto_valid_but_still_hold(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            envelope = self.signed_for(path, 1)
            r = verify_signed_anchor_receipt(path, envelope, self.trusted)
            self.assertTrue(r["pinned_signature_verified"])
            self.assertTrue(r["archive_binding_verified"])
            self.assertFalse(r["external_timestamp_authenticated"])
            self.assertFalse(r["witness_identity_independently_verified"])
            self.assertEqual(r["status"], "HOLD")
            self.assertFalse(r["live_execution_allowed"])

    def test_tamper_signature_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            e = self.signed_for(path, 1)
            raw = bytearray(base64.b64decode(e["signature_b64"]))
            raw[-1] ^= 1
            e["signature_b64"] = base64.b64encode(raw).decode("ascii")
            r = verify_signed_anchor_receipt(path, e, self.trusted)
            self.assertIn("SIGNATURE_INVALID", r["reasons"])
            self.assertFalse(r["pinned_signature_verified"])

    def test_signature_attached_to_other_series_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            e = self.signed_for(path, 1)
            e["payload"]["series_id"] = "synthetic-other-event"
            r = verify_signed_anchor_receipt(path, e, self.trusted)
            self.assertIn("ARCHIVE_EVENT_BINDING_MISMATCH", r["reasons"])

    def test_signature_replayed_for_other_game_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            e = self.signed_for(path, 1)
            e["payload"]["record_index"] = 2
            r = verify_signed_anchor_receipt(path, e, self.trusted)
            self.assertIn("ARCHIVE_EVENT_BINDING_MISMATCH", r["reasons"])

    def test_cross_archive_replay_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            e = self.signed_for(path, 1)
            other = Path(d) / "other.jsonl"
            from research.kpl_v11_forecast_archive import archive_forecast
            from ops.tests.test_kpl_v12_anchor_qualification import synthetic_forecast
            row = synthetic_forecast(2, 1)
            archive_forecast(other, row)
            r = verify_signed_anchor_receipt(other, e, self.trusted)
            self.assertIn("ARCHIVE_EVENT_BINDING_MISMATCH", r["reasons"])

    def test_wrong_pubkey_pin_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            trusted = copy.deepcopy(self.trusted)
            trusted["synthetic-witness"]["spki_sha256"] = "0" * 64
            r = verify_signed_anchor_receipt(path, self.signed_for(path, 1), trusted)
            self.assertIn("PINNED_PUBLIC_KEY_MISMATCH", r["reasons"])

    def test_wrong_key_id_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            e = self.signed_for(path, 1, nonce="synthetic-nonce-keyid")
            e["key_id"] = "forged-official-key"
            self.assertIn("KEY_NOT_PINNED",
                          verify_signed_anchor_receipt(path, e, self.trusted)["reasons"])

    def test_unpinned_key_ring_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            self.assertIn("KEY_NOT_PINNED",
                          verify_signed_anchor_receipt(path, self.signed_for(path, 1), {})["reasons"])

    def test_self_claimed_verified_field_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            e = self.signed_for(path, 1)
            e["verified"] = True
            self.assertIn("INVALID_SIGNED_ENVELOPE",
                          verify_signed_anchor_receipt(path, e, self.trusted)["reasons"])

    def test_post_game_witness_cannot_be_used(self):
        with tempfile.TemporaryDirectory() as d:
            path, rows, _, _ = make_archive(d, n_series=2)
            e = self.signed_for(path, 1)
            e["payload"]["witnessed_at"] = rows[0]["game_start_at"]
            e = self.sign(e["payload"])
            self.assertIn("WITNESS_TIME_INVALID",
                          verify_signed_anchor_receipt(path, e, self.trusted)["reasons"])

    def test_malformed_base64_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            e = self.signed_for(path, 1)
            e["signature_b64"] = "!!!"
            self.assertIn("INVALID_SIGNATURE_ENCODING",
                          verify_signed_anchor_receipt(path, e, self.trusted)["reasons"])

    def test_no_openssl_is_hold(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            e = self.signed_for(path, 1)
            with patch("research.kpl_v14_signed_anchor.subprocess.run", side_effect=FileNotFoundError):
                r = verify_signed_anchor_receipt(path, e, self.trusted)
            self.assertFalse(r["pinned_signature_verified"])
            self.assertIn("CRYPTO_BACKEND_UNAVAILABLE", r["reasons"])

    def test_unsupported_public_key_algorithm_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            rsa_priv = Path(d) / "synthetic-rsa-private.pem"
            subprocess.run(["openssl", "genpkey", "-algorithm", "RSA",
                            "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(rsa_priv)],
                           capture_output=True, check=True)
            pem = subprocess.run(["openssl", "pkey", "-in", str(rsa_priv),
                                  "-pubout"], capture_output=True, check=True).stdout
            der = subprocess.run(["openssl", "pkey", "-pubin", "-inform", "PEM",
                                  "-outform", "DER"], input=pem,
                                 capture_output=True, check=True).stdout
            trusted = {"synthetic-witness": {
                "public_key_pem": pem.decode("ascii"),
                "spki_sha256": hashlib.sha256(der).hexdigest()}}
            self.assertIn("UNSUPPORTED_OR_INVALID_PUBLIC_KEY",
                          verify_signed_anchor_receipt(path, self.signed_for(path, 1), trusted)["reasons"])

    def test_malformed_public_key_config_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            trusted = copy.deepcopy(self.trusted)
            trusted["synthetic-witness"]["public_key_pem"] = "not a public key"
            self.assertIn("INVALID_PIN_CONFIG",
                          verify_signed_anchor_receipt(path, self.signed_for(path, 1), trusted)["reasons"])

    def test_batch_all_signatures_valid_still_hold(self):
        with tempfile.TemporaryDirectory() as d:
            path, rows, _, _ = make_archive(d, n_series=2)
            envelopes = [self.signed_for(path, i) for i in range(1, len(rows)+1)]
            r = audit_signed_anchor_batch(path, envelopes, self.trusted)
            self.assertTrue(r["signed_receipt_coverage_passed"])
            self.assertEqual(r["signed_receipt_count"], len(rows))
            self.assertEqual(r["status"], "HOLD")
            self.assertFalse(r["production_recommendations"] != "DISABLED")
            self.assertFalse(r["external_timestamp_authenticated"])

    def test_batch_duplicate_nonce_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, rows, _, _ = make_archive(d, n_series=2)
            envelopes = [self.signed_for(path, i, nonce="synthetic-global-nonce")
                         for i in range(1, len(rows)+1)]
            r = audit_signed_anchor_batch(path, envelopes, self.trusted)
            self.assertIn("DUPLICATE_ANCHOR_NONCE", r["reasons"])

    def test_batch_missing_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            r = audit_signed_anchor_batch(path, [self.signed_for(path, 1)], self.trusted)
            self.assertIn("SIGNATURE_COVERAGE_INCOMPLETE", r["reasons"])

    def test_batch_invalid_one_signature_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, rows, _, _ = make_archive(d, n_series=2)
            es = [self.signed_for(path, i) for i in range(1, len(rows)+1)]
            es[-1]["payload"]["prediction_id"] = "other"
            r = audit_signed_anchor_batch(path, es, self.trusted)
            self.assertIn("SIGNED_RECEIPT_INVALID", r["reasons"])

    def test_unhashable_key_id_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d, n_series=2)
            e = self.signed_for(path, 1)
            e["key_id"] = []
            r = verify_signed_anchor_receipt(path, e, self.trusted)
            self.assertIn("INVALID_SIGNED_ENVELOPE", r["reasons"])


if __name__ == "__main__":
    unittest.main()
