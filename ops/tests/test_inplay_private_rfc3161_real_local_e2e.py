"""Actual OpenSSL RFC3161 integration, with ephemeral LOCAL TEST certs only.

No external TSA, network, bookmaker data or user screenshots. The signing key
and CA are created only inside a private TemporaryDirectory during each CI
test run; they MUST NOT be committed, uploaded or treated as trusted anchors.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_forward_private_seal import seal_candidate
from inplay_private_rfc3161_handoff import make_query, verify_response
from test_inplay_forward_private_seal import input_case, NOW as ORIGINAL_NOW


def _run(*args):
    """Never include generated private keys in error output."""
    process = subprocess.run(["openssl", *map(str, args)], capture_output=True,
                             text=True, check=False, timeout=30)
    if process.returncode:
        raise AssertionError("LOCAL_OPENSSL_COMMAND_FAILED:" + str(args[:2]))
    return process


def _iso_shift(value, delta):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (dt + delta).isoformat().replace("+00:00", "Z")


def _case_at(now):
    """Move *all* synthetic source/fixture/quote/screenshot clocks together."""
    case = input_case()
    delta = now - ORIGINAL_NOW
    fixture = case["fixture"]
    for field in ("kickoff_utc", "expected_identity_sealed_utc"):
        fixture[field] = _iso_shift(fixture[field], delta)
    for obs in case["observations"]:
        for field in ("kickoff_utc", "captured_utc", "source_updated_utc",
                      "last_material_event_utc"):
            obs[field] = _iso_shift(obs[field], delta)
    for field in ("captured_utc", "upstream_updated_utc"):
        case["quote"][field] = _iso_shift(case["quote"][field], delta)
    case["screenshot_manifest"]["screenshot"]["observed_at_utc"] = _iso_shift(
        case["screenshot_manifest"]["screenshot"]["observed_at_utc"], delta)
    case["fixture_seal_bytes"] = json.dumps({
        "fixture": fixture, "provenance_notice": "SELF_DECLARED_NOT_ATTESTED"
    }, sort_keys=True, ensure_ascii=False).encode("utf-8")
    case["now"] = now
    return case


class RealOpenSSLTestTSA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This is an integration test, not a mock: fail if OpenSSL unavailable.
        if shutil.which("openssl") is None:
            raise AssertionError("OPENSSL_REQUIRED_FOR_REAL_INTEGRATION_TEST")
        cls._temp = tempfile.TemporaryDirectory(prefix="fake-local-tsa-")
        cls.base = Path(cls._temp.name)
        root_key = cls.base / "root.key"
        cls.ca = cls.base / "root.pem"
        tsa_key = cls.base / "tsa.key"
        tsa_csr = cls.base / "tsa.csr"
        tsa_cert = cls.base / "tsa.pem"
        extension = cls.base / "tsa.ext"
        extension.write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature\n"
            "extendedKeyUsage=critical,timeStamping\n"
            "subjectKeyIdentifier=hash\n"
            "authorityKeyIdentifier=keyid,issuer\n",
            encoding="ascii")
        _run("req", "-x509", "-new", "-newkey", "rsa:2048", "-nodes",
             "-sha256", "-days", "1", "-subj", "/CN=Ephemeral Test Root",
             "-keyout", root_key, "-out", cls.ca)
        _run("req", "-new", "-newkey", "rsa:2048", "-nodes",
             "-subj", "/CN=Ephemeral RFC3161 Test TSA",
             "-keyout", tsa_key, "-out", tsa_csr)
        _run("x509", "-req", "-in", tsa_csr,
             "-CA", cls.ca, "-CAkey", root_key, "-CAcreateserial",
             "-days", "1", "-sha256", "-extfile", extension, "-out", tsa_cert)
        serial = cls.base / "serial"
        serial.write_text("01\n", encoding="ascii")
        cls.config = cls.base / "tsa.cnf"
        cls.config.write_text(
            "[tsa]\ndefault_tsa=tsa1\n"
            "[tsa1]\nserial=" + str(serial) + "\n"
            "signer_cert=" + str(tsa_cert) + "\n"
            "signer_key=" + str(tsa_key) + "\n"
            "signer_digest=sha256\n"
            "default_policy=1.2.3.4.5.6\n"
            "other_policies=1.2.3.4.5.6\n"
            "digests=sha256\naccuracy=secs:1\nordering=yes\n"
            "tsa_name=yes\ness_cert_id_chain=no\n",
            encoding="ascii")

    @classmethod
    def tearDownClass(cls):
        cls._temp.cleanup()

    def _new_archive(self, now=None, *, changed=False):
        # UTC source assertions are synthetic, synchronized and never
        # confused with actual provider feed update timestamps.
        stamp = now or datetime.now(timezone.utc).replace(microsecond=0)
        case = _case_at(stamp)
        if changed:
            case["quote_raw_bytes"] += b"-alternate-synthetic-quote"
        private = self.base / ("case_" + str(len(list(self.base.glob("case_*")))))
        private.mkdir()
        return Path(seal_candidate(**case, destination=private)["private_archive"]), private

    def _make_timestamp(self, archive, directory):
        request = directory / "request.tsq"
        result = make_query(archive, request)  # Actual OpenSSL
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        reply = directory / "response.tsr"
        _run("ts", "-reply", "-config", self.config,
             "-queryfile", request, "-out", reply)
        return request, reply

    def test_real_local_signature_digest_and_nonce_are_verified(self):
        archive, directory = self._new_archive()
        request, reply = self._make_timestamp(archive, directory)
        result = verify_response(archive, request, reply, self.ca)
        self.assertEqual(result["status"], "RESEARCH_ONLY", result)
        self.assertTrue(result["cryptographic_imprint_check_passed"])
        self.assertFalse(result["issuer_policy_independently_approved"])
        self.assertFalse(result["independently_timestamped"])
        self.assertFalse(result["provider_data_authenticated"])
        self.assertFalse(result["live_market_executable_verified"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["model_scoring_eligible"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(result["certified_forward_samples"], 0)
        self.assertIsNone(result["recommendation"])

    def test_actual_nonce_mismatch_rejected_even_if_digest_matches(self):
        archive, directory = self._new_archive()
        original_query, reply = self._make_timestamp(archive, directory)
        different_query = directory / "unrelated_nonce.tsq"
        make_query(archive, different_query)
        self.assertNotEqual(original_query.read_bytes(), different_query.read_bytes())
        result = verify_response(archive, different_query, reply, self.ca)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "OPENSSL_SIGNATURE_OR_IMPRINT_FAILED")

    def test_actual_different_archive_and_wrong_ca_rejected(self):
        archive, directory = self._new_archive()
        request, reply = self._make_timestamp(archive, directory)
        other_archive, _ = self._new_archive(changed=True)
        result = verify_response(other_archive, request, reply, self.ca)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "OPENSSL_SIGNATURE_OR_IMPRINT_FAILED")
        invalid_ca = directory / "not-a-ca.pem"
        invalid_ca.write_text("THIS IS NOT A CA\n", encoding="ascii")
        result = verify_response(archive, request, reply, invalid_ca)
        self.assertEqual(result["status"], "HOLD")

    def test_actual_signed_token_minted_after_time_window_rejected(self):
        old = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
        archive, directory = self._new_archive(now=old)
        request, reply = self._make_timestamp(archive, directory)
        result = verify_response(archive, request, reply, self.ca)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "TSA_TIME_NOT_TIMELY_FOR_THIS_CAPTURE")


if __name__ == "__main__":
    unittest.main()
