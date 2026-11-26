"""Receipt replay, tampering, and bounded multiprocess stress tests."""
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

OPS = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, OPS)
from prematch_raw_archive import archive_response
from prematch_evidence_chain import append_evidence, verify_evidence_chain
from prematch_integrity_report import evidence_integrity_report
from prematch_trusted_receipt import verify_receipt, replay_receipt

WORKER = """import sys,time
sys.path.insert(0,sys.argv[1])
from prematch_raw_archive import archive_response
from prematch_evidence_chain import append_evidence
root=sys.argv[2]
for n in range(10):
 raw=('worker-'+sys.argv[3]+'-'+str(n)).encode()
 archive=archive_response(raw,directory=root)
 for attempt in range(300):
  try:
   append_evidence(root,archive)
   break
  except BlockingIOError:
   time.sleep(.005)
 else:
  sys.exit(3)
"""


class TestTrustedReceipt(unittest.TestCase):
    def test_signed_receipt_and_replay_fail_closed(self):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            self.skipTest("optional cryptography dependency unavailable")
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        raw = b'{"provider":"sandbox"}'
        receipt = {"provider_id": "sandbox", "key_id": "sandbox-key",
                   "sha256": hashlib.sha256(raw).hexdigest(),
                   "captured_at_utc": "2026-10-24T01:00:00Z"}
        receipt["signature_b64"] = base64.b64encode(private.sign(json.dumps(
            receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())).decode()
        keys = {"sandbox-key": public}
        with tempfile.TemporaryDirectory() as root:
            archived = archive_response(raw, directory=root)
            append_evidence(root, archived)
            result = replay_receipt(root, receipt, pinned_keys=keys,
                                    expected_provider="sandbox",
                                    trusted_clock="2026-10-24T01:00:30Z")
            self.assertTrue(result["signature_verified"])
            self.assertFalse(result["trusted_timestamp_verified"])
            self.assertEqual(result["status"], "HOLD")
            self.assertIn("TIMESTAMP_AUTHORITY_NOT_VERIFIED", result["rejection_reasons"])
            altered = dict(receipt, provider_id="other")
            self.assertFalse(verify_receipt(raw, altered, pinned_keys=keys,
                                            expected_provider="sandbox")["signature_verified"])
            Path(archived["path"]).write_bytes(b"tampered")
            self.assertIn("ARCHIVE_REPLAY_FAILED", replay_receipt(
                root, receipt, pinned_keys=keys, expected_provider="sandbox")["rejection_reasons"])

    def test_integrity_inventory(self):
        with tempfile.TemporaryDirectory() as root:
            archived = archive_response(b"first", directory=root)
            append_evidence(root, archived)
            self.assertEqual(evidence_integrity_report(root)["status"], "RESEARCH_ONLY")
            archive_response(b"orphan", directory=root)
            self.assertIn("UNREFERENCED_ARCHIVE_FOUND",
                          evidence_integrity_report(root)["rejection_reasons"])

    def test_80_cross_process_appends(self):
        with tempfile.TemporaryDirectory() as root:
            children = [subprocess.Popen(
                [sys.executable, "-c", WORKER, OPS, root, str(i)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(8)]
            for child in children:
                _, err = child.communicate(timeout=45)
                self.assertEqual(child.returncode, 0, err.decode())
            entries = verify_evidence_chain(root)
            self.assertEqual(len(entries), 80)
            self.assertEqual([e["index"] for e in entries], list(range(80)))
            report = evidence_integrity_report(root)
            self.assertTrue(report["chain_verified"])
            self.assertEqual(report["unique_archive_digests"], 80)


if __name__ == "__main__":
    unittest.main()
