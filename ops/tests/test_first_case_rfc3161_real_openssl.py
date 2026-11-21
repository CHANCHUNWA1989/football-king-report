"""Real OpenSSL RFC3161 integration over SYNTHETIC unsigned football evidence.

Private keys and test TSA certs are generated only in ephemeral test folders.
The self-controlled TSA root is not an independently trusted provider.
Even real OpenSSL Verification: OK must remain HOLD, certified=0, no bets.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from first_case_rfc3161_link import check
from test_first_case_rfc3161_link import bundle, encoded

OPENSSL = shutil.which("openssl")


def command(*arguments):
    return subprocess.run(
        arguments, check=True, timeout=30,
        capture_output=True, text=True,
    )


@unittest.skipUnless(OPENSSL, "OpenSSL executable not installed")
class FirstCaseRFC3161RealOpenSSLTests(unittest.TestCase):
    """Offline cryptographic rehearsal, never source or independent TSA proof."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="synthetic-rfc3161-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.root_cert = cls.root / "synthetic-root.crt"
        root_key = cls.root / "synthetic-root.key"
        tsa_key = cls.root / "synthetic-tsa.key"
        tsa_csr = cls.root / "synthetic-tsa.csr"
        tsa_cert = cls.root / "synthetic-tsa.crt"

        command(OPENSSL, "req", "-new", "-x509", "-nodes",
                "-newkey", "rsa:2048", "-sha256", "-days", "2",
                "-subj", "/CN=UNTRUSTED Synthetic Test Root",
                "-keyout", str(root_key), "-out", str(cls.root_cert),
                "-addext", "basicConstraints=critical,CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign")
        command(OPENSSL, "req", "-new", "-nodes", "-newkey",
                "rsa:2048", "-sha256",
                "-subj", "/CN=UNTRUSTED Synthetic Test TSA",
                "-keyout", str(tsa_key), "-out", str(tsa_csr))
        extensions = cls.root / "tsa_extensions.cnf"
        extensions.write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature\n"
            "extendedKeyUsage=critical,timeStamping\n"
            "subjectKeyIdentifier=hash\n"
            "authorityKeyIdentifier=keyid,issuer\n",
            encoding="ascii")
        command(OPENSSL, "x509", "-req", "-in", str(tsa_csr),
                "-CA", str(cls.root_cert), "-CAkey", str(root_key),
                "-CAcreateserial", "-out", str(tsa_cert), "-days", "2",
                "-sha256", "-extfile", str(extensions))

        serial = cls.root / "serial.txt"
        serial.write_text("01\n", encoding="ascii")
        config = cls.root / "tsa.cnf"
        config.write_text(
            "[tsa]\ndefault_tsa=tsa_config\n"
            "[tsa_config]\n"
            f"serial = {serial}\n"
            f"signer_cert = {tsa_cert}\n"
            f"certs = {cls.root_cert}\n"
            f"signer_key = {tsa_key}\n"
            "signer_digest = sha256\n"
            "default_policy = 1.3.6.1.4.1.13762.3\n"
            "other_policies = 1.3.6.1.4.1.13762.3\n"
            "digests = sha256\n"
            "accuracy = secs:1\n"
            "ordering = yes\n"
            "tsa_name = yes\n"
            "ess_cert_id_alg = sha256\n"
            "ess_cert_id_chain = no\n",
            encoding="ascii")

        # Claimed times are synthetic; the actual signed genTime is supplied
        # by this runner's local clock. Keep the fake fixture in the future.
        now = datetime.now(timezone.utc).replace(microsecond=0)
        forecast, quote, manifest = (json.loads(part) for part in bundle())
        for item in (forecast, quote, manifest):
            item["kickoff_utc"] = (now + timedelta(hours=2)).isoformat()
        forecast["captured_utc"] = (now - timedelta(minutes=5, seconds=30)).isoformat()
        quote["observed_utc"] = (now - timedelta(minutes=6, seconds=30)).isoformat()
        quote["captured_utc"] = (now - timedelta(minutes=6)).isoformat()
        manifest["created_utc"] = (now - timedelta(minutes=5)).isoformat()
        cls.forecast = encoded(forecast)
        cls.quote = encoded(quote)
        manifest["forecast_sha256"] = hashlib.sha256(cls.forecast).hexdigest()
        manifest["quote_sha256"] = hashlib.sha256(cls.quote).hexdigest()
        cls.manifest = encoded(manifest)
        cls.manifest_file = cls.root / "manifest.json"
        cls.manifest_file.write_bytes(cls.manifest)
        cls.query_file = cls.root / "request.tsq"
        cls.token = cls.root / "response.tsr"
        command(OPENSSL, "ts", "-query", "-data", str(cls.manifest_file),
                "-sha256", "-cert", "-out", str(cls.query_file))
        command(OPENSSL, "ts", "-reply", "-queryfile",
                str(cls.query_file), "-config", str(config),
                "-section", "tsa_config", "-out", str(cls.token))
        cls.expected_digest = hashlib.sha256(cls.manifest).hexdigest()

    def run_bridge(self, *, forecast=None, quote=None, manifest=None,
                   token=None, ca=None):
        return check(
            self.forecast if forecast is None else forecast,
            self.quote if quote is None else quote,
            self.manifest if manifest is None else manifest,
            token_path=self.token if token is None else token,
            ca_path=self.root_cert if ca is None else ca,
            openssl=OPENSSL,
        )

    def test_actual_openssl_signature_and_manifest_imprint_hold(self):
        # This does not use a mock runner, and the test TSA is self-controlled.
        out = self.run_bridge()
        self.assertTrue(out["byte_digest_binding_checked"], out)
        self.assertTrue(out["local_openssl_signature_and_imprint_checked"], out)
        self.assertEqual(out["manifest_sha256"], self.expected_digest)
        self.assertEqual(out["status"], "HOLD")
        self.assertFalse(out["tsa_trust_policy_verified"])
        self.assertFalse(out["forecast_capture_time_independently_authenticated"])
        self.assertFalse(out["market_quote_executable_authenticated"])
        self.assertEqual(out["certified_forward_case_count"], 0)
        self.assertFalse(out["positive_ev_verified"])
        self.assertFalse(out["eligible_for_model_scoring"])
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_rehashed_manifest_rejects_original_real_timestamp_token(self):
        changed = json.loads(self.manifest)
        original_created = datetime.fromisoformat(changed["created_utc"])
        changed["created_utc"] = (
            original_created + timedelta(seconds=1)).isoformat()
        other_manifest = encoded(changed)
        self.assertNotEqual(hashlib.sha256(other_manifest).digest(),
                            hashlib.sha256(self.manifest).digest())
        out = self.run_bridge(manifest=other_manifest)
        self.assertTrue(out["byte_digest_binding_checked"])
        self.assertFalse(out["local_openssl_signature_and_imprint_checked"])
        self.assertEqual(out["reason"], "TSA_SIGNATURE_OR_MANIFEST_IMPRINT_UNTRUSTED")
        self.assertEqual(out["certified_forward_case_count"], 0)

    def test_forged_forecast_pinned_into_rewritten_manifest_rejected(self):
        changed_forecast = json.loads(self.forecast)
        changed_forecast["probabilities_1x2"] = [.6, .2, .2]
        altered_forecast = encoded(changed_forecast)
        changed_manifest = json.loads(self.manifest)
        changed_manifest["forecast_sha256"] = hashlib.sha256(
            altered_forecast).hexdigest()
        out = self.run_bridge(
            forecast=altered_forecast, manifest=encoded(changed_manifest))
        self.assertTrue(out["byte_digest_binding_checked"])
        self.assertEqual(out["reason"], "TSA_SIGNATURE_OR_MANIFEST_IMPRINT_UNTRUSTED")
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["certified_forward_case_count"], 0)

    def test_token_corrupted_or_wrong_ca_holds(self):
        corrupted = self.root / "tampered.tsr"
        token_bytes = self.token.read_bytes()
        corrupted.write_bytes(bytes([token_bytes[0] ^ 1]) + token_bytes[1:])
        out = self.run_bridge(token=corrupted)
        self.assertFalse(out["local_openssl_signature_and_imprint_checked"])
        self.assertEqual(out["status"], "HOLD")
        # Present an untrusted non-CA as a purported trust anchor.
        wrong = self.root / "synthetic-tsa.crt"
        out = self.run_bridge(ca=wrong)
        self.assertEqual(out["status"], "HOLD")
        self.assertFalse(out["tsa_trust_policy_verified"])
        self.assertEqual(out["certified_forward_case_count"], 0)


if __name__ == "__main__":
    unittest.main()
