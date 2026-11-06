"""Key revocation, RFC3161 fail-closed, and extended multiprocess stress."""
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

OPS = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, OPS)
from prematch_key_registry import verify_with_registry
from prematch_rfc3161_boundary import verify_rfc3161_token
from prematch_evidence_chain import verify_evidence_chain
from prematch_integrity_report import evidence_integrity_report

WORKER = """import sys,time
sys.path.insert(0,sys.argv[1])
from prematch_raw_archive import archive_response
from prematch_evidence_chain import append_evidence
for n in range(25):
 archive=archive_response(('load-'+sys.argv[3]+'-'+str(n)).encode(),directory=sys.argv[2])
 for retry in range(1000):
  try:
   append_evidence(sys.argv[2],archive)
   break
  except BlockingIOError:
   time.sleep(.003)
 else:
  sys.exit(5)
"""


class TestPhaseNine(unittest.TestCase):
    def test_key_revocation_and_rotation(self):
        raw = b"test"
        receipt = {"key_id": "k-old", "provider_id": "sandbox",
                   "captured_at_utc": "2026-10-24T00:00:00Z",
                   "sha256": hashlib.sha256(raw).hexdigest(),
                   "signature_b64": "bad"}
        record = {"public_key_pem": b"not-a-real-key", "provider_id": "sandbox",
                  "valid_from_utc": "2026-01-01T00:00:00Z",
                  "valid_until_utc": "2027-01-01T00:00:00Z", "revoked": True}
        result = verify_with_registry(raw, receipt, registry={"k-old": record},
                                      expected_provider="sandbox")
        self.assertIn("KEY_REVOKED", result["rejection_reasons"])
        record["revoked"] = False
        result = verify_with_registry(raw, receipt, registry={"k-old": record},
                                      expected_provider="sandbox")
        self.assertIn("SIGNATURE_INVALID", result["rejection_reasons"])
        record["valid_until_utc"] = "2026-01-01T00:00:00Z"
        result = verify_with_registry(raw, receipt, registry={"k-old": record},
                                      expected_provider="sandbox")
        self.assertIn("KEY_OUTSIDE_VALIDITY", result["rejection_reasons"])

    def test_rfc3161_missing_root_and_invalid_token(self):
        self.assertEqual(verify_rfc3161_token(b"raw", b"invalid")["reason"],
                         "TSA_TRUST_ROOT_NOT_CONFIGURED")
        result = verify_rfc3161_token(b"raw", b"invalid",
                                     tsa_ca_pem=b"-----BEGIN CERTIFICATE-----\ninvalid")
        self.assertIn(result["reason"],
                      ("RFC3161_VERIFICATION_FAILED", "RFC3161_VERIFIER_UNAVAILABLE"))

    def test_200_cross_process_appends(self):
        with tempfile.TemporaryDirectory() as root:
            children = [subprocess.Popen(
                [sys.executable, "-c", WORKER, OPS, root, str(i)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(8)]
            for child in children:
                _, err = child.communicate(timeout=90)
                self.assertEqual(child.returncode, 0, err.decode())
            entries = verify_evidence_chain(root)
            self.assertEqual(len(entries), 200)
            self.assertEqual([entry["index"] for entry in entries], list(range(200)))
            self.assertEqual(evidence_integrity_report(root)["status"], "RESEARCH_ONLY")


if __name__ == "__main__":
    unittest.main()
