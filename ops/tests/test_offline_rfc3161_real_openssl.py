"""Real OpenSSL-generated RFC3161 round-trip tests; local CA is test-only."""
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_rfc3161_verify import verify_rfc3161_token


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL unavailable")
class TestRealRFC3161RoundTrip(unittest.TestCase):
    def test_real_token_valid_and_tampered_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def command(*args):
                subprocess.run(["openssl", *map(str, args)], check=True,
                               capture_output=True, timeout=20)

            command("req", "-x509", "-newkey", "rsa:2048",
                    "-keyout", root / "ca.key", "-out", root / "ca.pem",
                    "-nodes", "-days", "1", "-subj", "/CN=Local Test Root")
            command("req", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", root / "tsa.key", "-out", root / "tsa.csr",
                    "-subj", "/CN=Local Test TSA")
            (root / "ext.cnf").write_text(
                "basicConstraints=CA:FALSE\n"
                "keyUsage=critical,digitalSignature\n"
                "extendedKeyUsage=critical,timeStamping\n")
            command("x509", "-req", "-in", root / "tsa.csr",
                    "-CA", root / "ca.pem", "-CAkey", root / "ca.key",
                    "-CAcreateserial", "-out", root / "tsa.pem",
                    "-days", "1", "-extfile", root / "ext.cnf")
            (root / "serial").write_text("01\n")
            evidence = root / "evidence.json"
            evidence.write_bytes(b'{"timestamp":"test-only"}')
            (root / "tsa.cnf").write_text(
                "[tsa_config]\n"
                f"serial = {root / 'serial'}\n"
                f"signer_cert = {root / 'tsa.pem'}\n"
                f"signer_key = {root / 'tsa.key'}\n"
                "signer_digest = sha256\n"
                "default_policy = 1.2.3.4.1\n"
                "digests = sha256\n"
                "accuracy = secs:1\n"
                "ordering = yes\n"
                "tsa_name = yes\n"
                "ess_cert_id_chain = no\n")
            command("ts", "-query", "-data", evidence, "-sha256", "-cert",
                    "-out", root / "request.tsq")
            command("ts", "-reply", "-queryfile", root / "request.tsq",
                    "-config", root / "tsa.cnf", "-section", "tsa_config",
                    "-out", root / "response.tsr")
            token = root / "token.der"
            command("ts", "-reply", "-in", root / "response.tsr",
                    "-token_out", "-out", token)
            arguments = dict(
                token_path=token, evidence_path=evidence,
                ca_bundle_path=root / "ca.pem",
                expected_ca_bundle_sha256=hashlib.sha256(
                    (root / "ca.pem").read_bytes()).hexdigest(),
                expected_token_sha256=hashlib.sha256(token.read_bytes()).hexdigest())
            result = verify_rfc3161_token(**arguments)
            self.assertEqual(result["status"], "RESEARCH_ONLY", result)
            self.assertTrue(result["rfc3161_signature_verified"])
            self.assertTrue(result["tsa_certificate_chain_verified"])
            self.assertFalse(result["trusted_timestamp_authority_verified"])
            self.assertFalse(result["tsa_operator_identity_verified"])
            self.assertFalse(result["prematch_capture_independence_verified"])
            self.assertEqual(result["production_recommendations"], "DISABLED")
            evidence.write_bytes(b'{"timestamp":"tampered"}')
            self.assertEqual(verify_rfc3161_token(**arguments)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
