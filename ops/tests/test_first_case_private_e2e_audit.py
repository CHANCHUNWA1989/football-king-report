"""End-to-end private evidence replay tests; synthetic events, NO certifications."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops import private_response_capture as capture
from first_case_private_quote_link import create as seal
from first_case_private_e2e_audit import inspect
from test_first_case_private_quote_link import event, CTX, PARAMS, NOW
from test_first_case_rfc3161_link import bundle, encoded

OPENSSL = shutil.which("openssl")


class FirstCasePrivateE2EReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="synthetic-private-case-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.pack = self.base/"private-pack"
        self.private = self.base/"private-case"
        self.private.mkdir(mode=0o700)
        self.forecast = self.private/"forecast.json"
        self.quote = self.private/"quote.json"
        self.manifest = self.private/"manifest.json"
        self.token = self.base/"synthetic-token.tsr"
        self.ca = self.base/"synthetic-ca.pem"
        self.token.write_bytes(b"UNTRUSTED-TEST-TOKEN")
        self.ca.write_bytes(b"UNTRUSTED-TEST-CA")
        self.forecast.write_bytes(bundle()[0])
        os.chmod(self.forecast, 0o600)
        self.original = event()
        with capture.CaptureSession(self.pack, **CTX) as session:
            session.record(
                encoded([self.original]),
                path="/sports/soccer_germany_bundesliga/odds/",
                params=PARAMS, secret="NEVER_A_REAL_KEY",
                quota={"used":1,"remaining":490,"last":1},
                requested=datetime(2026,11,21,10,0,10,tzinfo=timezone.utc),
                completed=datetime(2026,11,21,10,0,30,tzinfo=timezone.utc))
            self.pin = session.seal()["manifest_sha256"]
        seal(self.pack, self.forecast, **CTX, expected_manifest_sha256=self.pin,
             bookmaker_id="betfair", selection="HOME", quote_output=self.quote,
             manifest_output=self.manifest, now=NOW)

    def check(self, **overrides):
        fields=dict(
            source_sha=CTX["source_sha"], run_id=CTX["run_id"],
            attempt=CTX["attempt"], expected_manifest_sha256=self.pin,
            token_path=self.token, ca_path=self.ca, now=NOW+timedelta(minutes=1),
        )
        fields.update(overrides)
        return inspect(self.pack, self.forecast, self.quote, self.manifest, **fields)

    @staticmethod
    def verified(*args, **kwargs):
        # Controlled mock - never interprets fake token as real cert.
        return {"local_openssl_signature_and_imprint_checked": True,
                "tsa_gen_time_utc_claim": "2026-11-21T10:02:30Z"}

    def test_original_pack_quote_manifest_and_local_token_gate_all_hold(self):
        with patch("first_case_private_e2e_audit.verify_token",
                   side_effect=self.verified) as verify:
            out=self.check()
        self.assertTrue(out["private_original_pack_replayed"],out)
        self.assertTrue(out["exact_original_quote_and_manifest_reconstructed"])
        self.assertTrue(out["local_rfc3161_manifest_signature_and_imprint_checked"])
        self.assertEqual(verify.call_count, 1)
        args=verify.call_args.args
        self.assertEqual(args[0],self.forecast.read_bytes())
        self.assertEqual(args[1],self.quote.read_bytes())
        self.assertEqual(args[2],self.manifest.read_bytes())
        self.assertEqual(out["manifest_sha256"],
                         hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["certified_forward_case_count"],0)
        self.assertFalse(out["forecast_origin_independently_authenticated"])
        self.assertFalse(out["tsa_trust_policy_verified"])
        self.assertFalse(out["eligible_for_model_scoring"])
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertNotIn("decimal_odds",out)
        self.assertNotIn("fixture_id_claim",out)
        self.assertNotIn("bookmaker_id_claim",out)

    def test_changed_quote_bytes_rejected_before_openssl(self):
        original=self.quote.read_bytes()
        self.quote.write_bytes(original.replace(b"1.96",b"1.97"))
        with patch("first_case_private_e2e_audit.verify_token") as verify:
            out=self.check()
        self.assertEqual(out["reason"],"SELECTED_QUOTE_DIFFERENT_FROM_ORIGINAL_RAW_RESPONSE")
        self.assertFalse(out["exact_original_quote_and_manifest_reconstructed"])
        verify.assert_not_called()

    def test_rehashed_forged_quote_and_manifest_not_from_source(self):
        obj=json.loads(self.quote.read_bytes())
        obj["decimal_odds"]=2.25
        changed=encoded(obj)
        self.quote.write_bytes(changed)
        manifest=json.loads(self.manifest.read_bytes())
        manifest["quote_sha256"]=hashlib.sha256(changed).hexdigest()
        self.manifest.write_bytes(encoded(manifest))
        with patch("first_case_private_e2e_audit.verify_token") as verify:
            out=self.check()
        self.assertEqual(out["reason"],"SELECTED_QUOTE_DIFFERENT_FROM_ORIGINAL_RAW_RESPONSE")
        verify.assert_not_called()
        self.assertEqual(out["certified_forward_case_count"],0)

    def test_wrong_manifest_raw_quote_digest_fails_reconstruction(self):
        manifest=json.loads(self.manifest.read_bytes())
        manifest["quote_sha256"]="0"*64
        self.manifest.write_bytes(encoded(manifest))
        with patch("first_case_private_e2e_audit.verify_token") as verify:
            out=self.check()
        self.assertEqual(out["reason"],"SEALED_MANIFEST_DIFFERENT_FROM_SOURCE_RECONSTRUCTION")
        verify.assert_not_called()

    def test_manifest_capture_time_rewrite_requires_original_tsa_token(self):
        # The old quote remains fresh at both 10:02:00 and 10:01:59.
        # Both byte sets can be structurally reconstructed, but only one can
        # be authenticated by an unaltered earlier external RFC3161 token.
        manifest=json.loads(self.manifest.read_bytes())
        manifest["created_utc"]="2026-11-21T10:01:59Z"
        self.manifest.write_bytes(encoded(manifest))
        with patch("first_case_private_e2e_audit.verify_token",return_value={
            "local_openssl_signature_and_imprint_checked":False,
            "reason":"TSA_SIGNATURE_OR_MANIFEST_IMPRINT_UNTRUSTED",
        }) as verify:
            out=self.check()
        self.assertEqual(verify.call_count,1)
        self.assertEqual(out["reason"],"RFC3161_MANIFEST_LINK_OR_LOCAL_SIGNATURE_FAILED")
        self.assertFalse(out["local_rfc3161_manifest_signature_and_imprint_checked"])
        self.assertEqual(out["certified_forward_case_count"],0)

    def test_wrong_source_pack_pin_context_and_provider_claim(self):
        for bad in ("0"*64,"b"*64):
            with self.subTest(pin=bad):
                with patch("first_case_private_e2e_audit.verify_token") as verify:
                    out=self.check(expected_manifest_sha256=bad)
                self.assertNotEqual(out["reason"],
                                    "ORIGINAL_PACK_AND_LOCAL_TIMESTAMP_REPLAY_PASS_EXTERNAL_TRUST_STILL_MISSING")
                verify.assert_not_called()
        q=json.loads(self.quote.read_bytes())
        q["provider"]=q["provider"].replace(self.pin,"0"*64)
        self.quote.write_bytes(encoded(q))
        with patch("first_case_private_e2e_audit.verify_token") as verify:
            out=self.check()
        self.assertEqual(out["reason"],"ORIGINAL_PRIVATE_PACK_NOT_PINNED_IN_QUOTE")
        verify.assert_not_called()

    def test_actual_token_verification_failure_is_not_ignored(self):
        out=self.check()
        self.assertEqual(out["reason"],"RFC3161_MANIFEST_LINK_OR_LOCAL_SIGNATURE_FAILED")
        self.assertFalse(out["local_rfc3161_manifest_signature_and_imprint_checked"])
        self.assertFalse(out["tsa_trust_policy_verified"])

    def test_token_timestamp_future_against_audit_clock_holds(self):
        with patch("first_case_private_e2e_audit.verify_token",return_value={
            "local_openssl_signature_and_imprint_checked": True,
            "tsa_gen_time_utc_claim":"2026-11-21T12:00:00Z"}):
            out=self.check()
        self.assertEqual(out["reason"],"TSA_TOKEN_SIGNED_AFTER_AUDIT_CLOCK")

    def test_symlink_and_world_readable_originals_are_rejected(self):
        self.quote.chmod(0o644)
        with patch("first_case_private_e2e_audit.verify_token") as verify:
            out=self.check()
        self.assertEqual(out["reason"],"PRIVATE_SOURCE_OR_TIMESTAMP_EVIDENCE_REJECTED")
        verify.assert_not_called()
        self.quote.chmod(0o600)
        real=self.quote.with_name("quote-hidden.json")
        self.quote.rename(real)
        self.quote.symlink_to(real)
        with patch("first_case_private_e2e_audit.verify_token") as verify:
            out=self.check()
        self.assertEqual(out["reason"],"PRIVATE_CASE_FILES_NOT_DISTINCT_OR_SAME_DIRECTORY")
        verify.assert_not_called()

    def test_pinned_capture_pack_tampered_after_source_read_rejected(self):
        before=capture.replay_records
        def change(*args, **kwargs):
            rows=before(*args, **kwargs)
            self.quote.write_bytes(self.quote.read_bytes()+b" ")
            return rows
        with patch("first_case_private_e2e_audit.capture.replay_records",
                   side_effect=change),patch(
                "first_case_private_e2e_audit.verify_token",
                side_effect=self.verified):
            out=self.check()
        self.assertEqual(out["reason"],"PRIVATE_ORIGINAL_CHANGED_DURING_REPLAY")
        self.assertFalse(out["local_rfc3161_manifest_signature_and_imprint_checked"])


@unittest.skipUnless(OPENSSL,"OpenSSL CLI not installed")
class FirstCasePrivateE2ERealCryptoTests(unittest.TestCase):
    def test_offline_replay_with_real_synthetic_rfc3161_token(self):
        # Use a new prospective synthetic fixture whose kickoff is in the
        # future relative to real OpenSSL genTime. Never a real sport result.
        now=datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory(prefix="synthetic-e2e-openssl-") as td:
            root=Path(td)
            pack=root/"capture"
            private=root/"private"
            private.mkdir(mode=0o700)
            forecast,quote,manifest=(private/x for x in
                                     ("forecast.json","quote.json","manifest.json"))
            f=json.loads(bundle()[0])
            f["kickoff_utc"]=(now+timedelta(hours=2)).isoformat()
            f["captured_utc"]=(now-timedelta(seconds=20)).isoformat()
            f["fixture_id"]="synthetic-live-e2e"
            forecast.write_bytes(encoded(f));forecast.chmod(0o600)
            e=event()
            e["id"]=f["fixture_id"]
            e["commence_time"]=f["kickoff_utc"]
            e["bookmakers"][0]["markets"][0]["last_update"]=(
                now-timedelta(seconds=65)).isoformat()
            with capture.CaptureSession(pack, **CTX) as s:
                s.record(
                    encoded([e]),path="/sports/soccer_germany_bundesliga/odds/",
                    params=PARAMS,secret="SYNTHETIC_NO_KEY",
                    quota={"used":1,"remaining":490,"last":1},
                    requested=now-timedelta(seconds=45),
                    completed=now-timedelta(seconds=35))
                pin=s.seal()["manifest_sha256"]
            seal(pack,forecast,**CTX,expected_manifest_sha256=pin,
                 bookmaker_id="betfair",selection="HOME",
                 quote_output=quote,manifest_output=manifest,
                 now=now-timedelta(seconds=10))
            cert=root/"root.pem";rootkey=root/"root.key"
            tsakey=root/"tsa.key";csr=root/"tsa.csr";tsacert=root/"tsa.crt"
            def run(*cmd):
                return subprocess.run([OPENSSL,*map(str,cmd)],
                                      check=True,timeout=20,
                                      capture_output=True,text=True)
            run("req","-new","-x509","-nodes","-newkey","rsa:2048",
                "-sha256","-days","2","-subj",
                "/CN=UNTRUSTED Local E2E Synthetic Root","-keyout",rootkey,
                "-out",cert,"-addext","basicConstraints=critical,CA:TRUE",
                "-addext","keyUsage=critical,keyCertSign,cRLSign")
            run("req","-new","-nodes","-newkey","rsa:2048","-sha256",
                "-subj","/CN=UNTRUSTED Synthetic E2E TSA",
                "-keyout",tsakey,"-out",csr)
            ext=root/"ext.cnf"
            ext.write_text("basicConstraints=critical,CA:FALSE\n"
                           "keyUsage=critical,digitalSignature\n"
                           "extendedKeyUsage=critical,timeStamping\n"
                           "subjectKeyIdentifier=hash\n"
                           "authorityKeyIdentifier=keyid,issuer\n")
            run("x509","-req","-in",csr,"-CA",cert,"-CAkey",rootkey,
                "-CAcreateserial","-out",tsacert,"-days","2",
                "-sha256","-extfile",ext)
            serial=root/"serial";serial.write_text("01\n")
            conf=root/"tsa.cnf";conf.write_text(
                "[tsa]\ndefault_tsa=tsa_config\n[tsa_config]\n"
                f"serial = {serial}\nsigner_cert = {tsacert}\n"
                f"certs = {cert}\nsigner_key = {tsakey}\n"
                "signer_digest = sha256\n"
                "default_policy = 1.3.6.1.4.1.13762.3\n"
                "other_policies = 1.3.6.1.4.1.13762.3\n"
                "digests = sha256\naccuracy = secs:1\n"
                "ordering = yes\ntsa_name = yes\n"
                "ess_cert_id_alg = sha256\ness_cert_id_chain = no\n")
            query=root/"tsq";token=root/"tsr"
            run("ts","-query","-data",manifest,"-sha256","-cert","-out",query)
            run("ts","-reply","-queryfile",query,"-config",conf,
                "-section","tsa_config","-out",token)
            result=inspect(
                pack,forecast,quote,manifest,**CTX,
                expected_manifest_sha256=pin,
                token_path=token,ca_path=cert,
                openssl=OPENSSL,now=datetime.now(timezone.utc)+timedelta(seconds=5))
            self.assertTrue(result["private_original_pack_replayed"],result)
            self.assertTrue(result["exact_original_quote_and_manifest_reconstructed"])
            self.assertTrue(result["local_rfc3161_manifest_signature_and_imprint_checked"])
            self.assertFalse(result["tsa_trust_policy_verified"])
            self.assertEqual(result["certified_forward_case_count"],0)
            self.assertEqual(result["production_recommendations"],"DISABLED")
            # Token was signed for the original private manifest, not any
            # newly rehashed/changed forecast model or source quote.
            altered=json.loads(quote.read_bytes());altered["decimal_odds"]=2.15
            quote.write_bytes(encoded(altered))
            reject=inspect(
                pack,forecast,quote,manifest,**CTX,
                expected_manifest_sha256=pin,
                token_path=token,ca_path=cert,
                openssl=OPENSSL,now=datetime.now(timezone.utc)+timedelta(seconds=5))
            self.assertFalse(reject["local_rfc3161_manifest_signature_and_imprint_checked"])
            self.assertEqual(reject["certified_forward_case_count"],0)


if __name__=="__main__":
    unittest.main()
