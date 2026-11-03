"""KPL V15 RFC3161 offline synthetic cert/token tests; no real trusted TSA."""
import base64
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from research.kpl_v11_forecast_archive import archive_forecast
from research.kpl_v14_signed_anchor import (
    build_unsigned_anchor_payload, canonical_signed_message)
from research.kpl_v15_rfc3161_offline import verify_rfc3161_offline


def run(*args, data=None, cwd=None):
    return subprocess.run(["openssl", *args], input=data, cwd=cwd,
                          capture_output=True, check=True, timeout=15).stdout


def stamp(dt):
    return dt.isoformat().replace("+00:00", "Z")


def cert_der(pem):
    return run("x509", "-inform", "PEM", "-outform", "DER", data=pem.encode())


class V15RFC3161Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._root = tempfile.TemporaryDirectory(prefix="kpl15-testa-")
        d = Path(cls._root.name)
        cls.folder = d
        run("req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(d / "root.key"), "-out", str(d / "root.pem"),
            "-days", "3", "-subj", "/CN=Synthetic V15 Test Root",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
        run("req", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(d / "tsa.key"), "-out", str(d / "tsa.csr"),
            "-subj", "/CN=Synthetic V15 TSA")
        ext = d / "tsa.ext"
        ext.write_text("basicConstraints=critical,CA:FALSE\n"
                       "keyUsage=critical,digitalSignature\n"
                       "extendedKeyUsage=critical,timeStamping\n"
                       "subjectKeyIdentifier=hash\n"
                       "authorityKeyIdentifier=keyid,issuer\n")
        run("x509", "-req", "-in", str(d / "tsa.csr"), "-CA",
            str(d / "root.pem"), "-CAkey", str(d / "root.key"),
            "-CAcreateserial", "-out", str(d / "tsa.pem"), "-days", "3",
            "-extfile", str(ext))
        cls.edprivate = d / "ed25519.key"
        run("genpkey", "-algorithm", "Ed25519", "-out", str(cls.edprivate))
        public = run("pkey", "-in", str(cls.edprivate), "-pubout")
        public_der = run("pkey", "-pubin", "-inform", "PEM",
                         "-outform", "DER", data=public)
        cls.edtrust = {"test-v15-ed25519": {
            "public_key_pem": public.decode("ascii"),
            "spki_sha256": hashlib.sha256(public_der).hexdigest()}}
        cls.rootpem = (d / "root.pem").read_text()
        cls.tsapem = (d / "tsa.pem").read_text()
        cls.tsa_trust = {
            "root_ca_pem": cls.rootpem,
            "root_cert_sha256": hashlib.sha256(cert_der(cls.rootpem)).hexdigest(),
            "tsa_cert_pem": cls.tsapem,
            "tsa_cert_sha256": hashlib.sha256(cert_der(cls.tsapem)).hexdigest(),
            "allowed_policies": ["1.3.6.1.4.1.55555.1"],
        }
        (d / "demoCA").mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls._root.cleanup()

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="kpl15-example-")
        self.addCleanup(self._temp.cleanup)
        self.folder_case = Path(self._temp.name)
        self.path = self.folder_case / "archive.jsonl"
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.now = now
        self.forecast = {
            "prediction_id": "synthetic-prospective-case", "series_id": "sim-bo7-001",
            "game_number": 1, "team_ids": ["sim-a", "sim-b"],
            "predicted_team_id": "sim-a", "probability": 0.56,
            "model_version": "offline-simulation", "phase": "PRE_GAME",
            "info_cutoff_at": stamp(now - timedelta(minutes=5, seconds=10)),
            "forecast_at": stamp(now - timedelta(minutes=5)),
            "game_start_at": stamp(now + timedelta(minutes=12)),
            "status": "RESEARCH_ONLY",
            "evidence": [{"source_id": "simulated-roster",
                          "kind": "team_form", "subject_game": 0,
                          "published_at": stamp(now - timedelta(minutes=12)),
                          "captured_at": stamp(now - timedelta(minutes=8))}]}
        archive_forecast(self.path, self.forecast)
        self.envelope = self._sign_for(stamp(now - timedelta(minutes=3)))

    def _sign_for(self, witnessed_at):
        payload = build_unsigned_anchor_payload(
            self.path, 1, witnessed_at=witnessed_at,
            nonce="v15-synthetic-nonce-unique-0001")
        msg = self.folder_case / "ed-message"
        sig = self.folder_case / "ed-signature"
        msg.write_bytes(canonical_signed_message(payload))
        run("pkeyutl", "-sign", "-rawin", "-inkey",
            str(self.edprivate), "-in", str(msg), "-out", str(sig))
        return {"payload": payload, "key_id": "test-v15-ed25519",
                "signature_b64": base64.b64encode(sig.read_bytes()).decode("ascii")}

    def _token(self, envelope=None, *, policy="1.3.6.1.4.1.55555.1",
               signer_pem=None):
        msg = self.folder_case / "tsa-data.bin"
        q = self.folder_case / "request.tsq"
        token = self.folder_case / "token.der"
        msg.write_bytes(json.dumps(envelope or self.envelope,
                                   sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=False, allow_nan=False).encode())
        run("ts", "-query", "-data", str(msg), "-sha256",
            "-cert", "-out", str(q))
        run("ts", "-reply", "-queryfile", str(q),
            "-signer", str(signer_pem or self.folder / "tsa.pem"),
            "-inkey", str(self.folder / "tsa.key"),
            "-chain", str(self.folder / "root.pem"),
            "-tspolicy", policy, "-out", str(token),
            "-token_out", cwd=self.folder)
        return base64.b64encode(token.read_bytes()).decode("ascii")

    def verify(self, token=None, *, envelope=None, tsa_trust=None, crl=None):
        return verify_rfc3161_offline(
            self.path, envelope or self.envelope, self.edtrust,
            token if token is not None else self._token(),
            tsa_trust if tsa_trust is not None else self.tsa_trust,
            revocation_crl_pem=crl)

    def test_valid_chain_imprint_time_but_revocation_missing_hold(self):
        r = self.verify()
        self.assertTrue(r["ed25519_pinned_signature_verified"])
        self.assertTrue(r["rfc3161_token_signature_and_imprint_verified"], r)
        self.assertTrue(r["tsa_certificate_chain_valid_at_gen_time"], r)
        self.assertTrue(r["tsa_timestamp_within_forecast_window"], r)
        self.assertFalse(r["revocation_status_locally_checked"])
        self.assertIn("REVOCATION_STATUS_UNAVAILABLE", r["reasons"])
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["live_execution_allowed"])

    def test_tampered_ed25519_signature_rejected(self):
        envelope = copy.deepcopy(self.envelope)
        envelope["signature_b64"] = base64.b64encode(b"\0" * 64).decode()
        self.assertIn("ED25519_RECEIPT_INVALID",
                      self.verify(envelope=envelope)["reasons"])

    def test_wrong_token_imprint_rejected(self):
        alternative = copy.deepcopy(self.envelope)
        alternative["key_id"] = "different"
        r = self.verify(token=self._token(alternative))
        self.assertIn("RFC3161_IMPRINT_SIGNATURE_OR_CERT_PATH_INVALID",
                      r["reasons"])

    def test_wrong_tsa_root_pin_rejected(self):
        trust = copy.deepcopy(self.tsa_trust)
        trust["root_cert_sha256"] = "f" * 64
        self.assertIn("PINNED_TSA_CERTIFICATE_MISMATCH",
                      self.verify(tsa_trust=trust)["reasons"])

    def test_wrong_tsa_leaf_pin_rejected(self):
        trust = copy.deepcopy(self.tsa_trust)
        trust["tsa_cert_sha256"] = "f" * 64
        self.assertIn("PINNED_TSA_CERTIFICATE_MISMATCH",
                      self.verify(tsa_trust=trust)["reasons"])

    def test_mismatched_tsa_policy_rejected(self):
        trust = copy.deepcopy(self.tsa_trust)
        trust["allowed_policies"] = ["1.3.6.1.4.1.55555.999"]
        self.assertIn("TSA_POLICY_NOT_ALLOWLISTED",
                      self.verify(tsa_trust=trust)["reasons"])

    def test_malformed_token_base64_rejected(self):
        self.assertIn("INVALID_RFC3161_TOKEN_ENCODING",
                      self.verify(token="not-valid-!!!!")["reasons"])

    def test_empty_tsa_trust_config_rejected(self):
        self.assertIn("INVALID_TSA_TRUST_CONFIG",
                      self.verify(tsa_trust={})["reasons"])

    def test_missing_crl_remains_hold_always(self):
        r = self.verify()
        self.assertFalse(r["external_timestamp_fully_trusted"])
        self.assertFalse(r["trust_anchor_independently_authenticated"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_malformed_crl_is_rejected(self):
        r = self.verify(crl="NOT A CRL")
        self.assertIn("INVALID_REVOCATION_EVIDENCE", r["reasons"])
        self.assertFalse(r["revocation_status_locally_checked"])

    def test_future_claimed_witness_time_rejected(self):
        # All signed fields are internally consistent, but TSA token produced
        # now cannot predate a signed claim of witnessing in the future.
        self.envelope = self._sign_for(stamp(self.now + timedelta(minutes=2)))
        r = self.verify()
        self.assertIn("TSA_TIME_OUTSIDE_SIGNED_FORECAST_WINDOW", r["reasons"])
        self.assertFalse(r["tsa_timestamp_within_forecast_window"])

    def test_post_game_tsa_timestamp_is_rejected(self):
        self.path.unlink()
        self.forecast["game_start_at"] = stamp(self.now - timedelta(seconds=30))
        archive_forecast(self.path, self.forecast)
        self.envelope = self._sign_for(stamp(self.now - timedelta(minutes=3)))
        r = self.verify()
        self.assertIn("TSA_TIME_OUTSIDE_SIGNED_FORECAST_WINDOW", r["reasons"])

    def test_cross_event_replayed_signature_rejected(self):
        envelope = copy.deepcopy(self.envelope)
        envelope["payload"]["series_id"] = "other-bo7"
        self.assertIn("ED25519_RECEIPT_INVALID", self.verify(envelope=envelope)["reasons"])

    def test_token_signed_by_other_cert_under_same_root_rejected(self):
        d = self.folder_case
        run("req", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(d / "attacker.key"), "-out", str(d / "attacker.csr"),
            "-subj", "/CN=Synthetic Wrong TSA")
        run("x509", "-req", "-in", str(d / "attacker.csr"),
            "-CA", str(self.folder / "root.pem"), "-CAkey",
            str(self.folder / "root.key"), "-CAcreateserial",
            "-out", str(d / "attacker.pem"), "-days", "3",
            "-extfile", str(self.folder / "tsa.ext"))
        # Keep a valid pinned TSA CA chain but timestamp signed with other TSA
        # cert/private key. Construct token manually with attacker key.
        msg = d / "wrong-msg"
        msg.write_bytes(json.dumps(self.envelope, sort_keys=True,
                                   separators=(",", ":"), ensure_ascii=False).encode())
        q, tok = d / "wrong.tsq", d / "wrong.der"
        run("ts", "-query", "-data", str(msg), "-sha256", "-cert", "-out", str(q))
        run("ts", "-reply", "-queryfile", str(q), "-signer", str(d / "attacker.pem"),
            "-inkey", str(d / "attacker.key"), "-chain",
            str(self.folder / "root.pem"), "-tspolicy", "1.3.6.1.4.1.55555.1",
            "-out", str(tok), "-token_out", cwd=self.folder)
        r = self.verify(token=base64.b64encode(tok.read_bytes()).decode())
        self.assertIn("PINNED_TSA_SIGNER_MISMATCH", r["reasons"])

    def test_expired_tsa_cert_at_token_generation_rejected(self):
        d = self.folder_case
        cfg = d / "ca.cnf"
        (d / "index.txt").write_text("")
        (d / "serial").write_text("01\n")
        cfg.write_text("[ca]\ndefault_ca=ca_default\n[ca_default]\n"
                       f"database={d / 'index.txt'}\nnew_certs_dir={d}\n"
                       f"serial={d / 'serial'}\nprivate_key={self.folder / 'root.key'}\n"
                       f"certificate={self.folder / 'root.pem'}\ndefault_md=sha256\n"
                       "policy=policy_any\nx509_extensions=tsa_ext\n"
                       "[policy_any]\ncommonName=supplied\n[tsa_ext]\n"
                       "basicConstraints=critical,CA:FALSE\n"
                       "keyUsage=critical,digitalSignature\n"
                       "extendedKeyUsage=critical,timeStamping\n")
        expired = d / "expired.pem"
        run("ca", "-batch", "-config", str(cfg), "-in",
            str(self.folder / "tsa.csr"), "-out", str(expired),
            "-startdate", "20200101000000Z", "-enddate", "20210101000000Z")
        trust = copy.deepcopy(self.tsa_trust)
        trust["tsa_cert_pem"] = run("x509", "-in", str(expired),
                                    "-outform", "PEM").decode("ascii")
        trust["tsa_cert_sha256"] = hashlib.sha256(cert_der(trust["tsa_cert_pem"])).hexdigest()
        r = self.verify(token=self._token(signer_pem=expired), tsa_trust=trust)
        self.assertIn("RFC3161_IMPRINT_SIGNATURE_OR_CERT_PATH_INVALID", r["reasons"])
        self.assertFalse(r["tsa_certificate_chain_valid_at_gen_time"])

    def test_openssl_unavailable_fails_closed(self):
        with patch("research.kpl_v15_rfc3161_offline.subprocess.run",
                   side_effect=FileNotFoundError):
            r = self.verify(token="YQ==")
        self.assertIn("CRYPTO_BACKEND_UNAVAILABLE", r["reasons"])

    def test_bogus_crl_pem_fails_closed(self):
        r = self.verify(crl="-----BEGIN X509 CRL-----\nAA==\n-----END X509 CRL-----")
        self.assertIn("CRL_REVOKED_STALE_OR_INVALID", r["reasons"])
        self.assertFalse(r["revocation_status_locally_checked"])


if __name__ == "__main__":
    unittest.main()
