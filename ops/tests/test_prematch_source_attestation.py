"""Offline signed-provider and sandbox replay tests, no live API or credentials."""
import base64
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prematch_source_attestation import verify_attestation
from prematch_raw_archive import archive_response, replay_response
from prematch_evidence_chain import append_evidence, verify_evidence_chain


class TestSourceAttestation(unittest.TestCase):
    def test_signature_and_timestamp_boundary(self):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            self.skipTest("cryptography not installed in this regression environment")
        # Signed-source suite runs fully in the pinned walk-forward workflow.
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo)
        raw = b'{"sandbox":true}'
        signature = base64.b64encode(private.sign(raw)).decode()
        args = dict(signature_b64=signature, public_key_pem=public,
                    timestamp_utc="2026-10-24T11:00:00Z",
                    trusted_time_utc="2026-10-24T11:00:30Z")
        result = verify_attestation(raw, **args)
        self.assertTrue(result["signature_verified"])
        self.assertFalse(result["trusted_timestamp_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(verify_attestation(raw + b"x", **args)["status"], "HOLD")
        self.assertEqual(verify_attestation(raw, **{**args,
            "trusted_time_utc": "2026-10-24T11:10:00Z"})["status"], "HOLD")

    def test_replay_sandbox_fixture_and_chain(self):
        with tempfile.TemporaryDirectory() as root:
            payload = b'{"provider_id":"sandbox","decimal_odds":{"home":2,"draw":3,"away":4}}'
            archived = archive_response(payload, directory=root)
            append_evidence(root, archived)
            self.assertEqual(replay_response(archived["path"],
                             expected_sha256=archived["sha256"]), payload)
            self.assertEqual(len(verify_evidence_chain(root)), 1)

    def test_symlink_ledger_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            external = Path(root) / "external"
            external.write_text("untrusted")
            (Path(root) / "evidence-ledger.jsonl").symlink_to(external)
            with self.assertRaises(ValueError):
                verify_evidence_chain(root)


if __name__ == "__main__":
    unittest.main()
