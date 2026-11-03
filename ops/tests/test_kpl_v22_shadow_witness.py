"""KPL V22 synthetic RFC3161 receipts, no real provider keys or KPL match data."""
import base64
import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from research.kpl_v20_shadow_trial import (
    register_shadow_trial, submit_shadow_decision)
from research.kpl_v22_shadow_witness import (
    audit_shadow_timestamp_bundle, prepare_shadow_timestamp_request,
    _verify_req_token, _decode_b64)


def run(*args, data=None):
    return subprocess.run(["openssl", *args], input=data, capture_output=True,
                          check=True, timeout=20).stdout


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


class V22TimestampTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="kpl-v22-synthetic-")
        d = Path(cls._tmp.name)
        cls.base = datetime.now(timezone.utc).replace(microsecond=0)
        cls.root = d
        cls.trialroot = d / "trialroot"
        cls.source = cls.trialroot / "v22-synthetic-trial"
        certdir = d / "certs"
        certdir.mkdir()
        cls.certdir = certdir
        run("req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(certdir/"root.key"), "-out", str(certdir/"root.pem"),
            "-days", "3", "-subj", "/CN=Synthetic KPL V22 Root",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
        run("req", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(certdir/"tsa.key"), "-out", str(certdir/"tsa.csr"),
            "-subj", "/CN=Synthetic KPL V22 TSA")
        ext = certdir / "tsa.ext"
        ext.write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature\n"
            "extendedKeyUsage=critical,timeStamping\n"
            "subjectKeyIdentifier=hash\n"
            "authorityKeyIdentifier=keyid,issuer\n")
        run("x509", "-req", "-in", str(certdir/"tsa.csr"),
            "-CA", str(certdir/"root.pem"),
            "-CAkey", str(certdir/"root.key"), "-CAcreateserial",
            "-out", str(certdir/"tsa.pem"), "-days", "3",
            "-extfile", str(ext))
        root = (certdir/"root.pem").read_text()
        tsa = (certdir/"tsa.pem").read_text()
        cls.trust = {
            "root_ca_pem": root,
            "root_cert_sha256": hashlib.sha256(
                run("x509", "-inform", "PEM", "-outform", "DER",
                    data=root.encode())).hexdigest(),
            "tsa_cert_pem": tsa,
            "tsa_cert_sha256": hashlib.sha256(
                run("x509", "-inform", "PEM", "-outform", "DER",
                    data=tsa.encode())).hexdigest(),
            "allowed_policies": ["1.3.6.1.4.1.55555.22"]}
        manifest = {
            "trial_id": "v22-synthetic-trial",
            "registration_at": iso(cls.base),
            "model_version": "synthetic-frozen-v22",
            "model_frozen_at": iso(cls.base-timedelta(days=1)),
            "series": [{
                "series_id": "synthetic-bo7-a",
                "team_ids": ["synthetic-A", "synthetic-B"],
                "first_game_start_at": iso(cls.base+timedelta(minutes=30)),
                "schedule_source_id": "synthetic-schedule-only"
            }]
        }
        with patch("research.kpl_v20_shadow_trial._utcnow",
                   return_value=cls.base):
            register_shadow_trial(cls.trialroot, manifest)
        for g in range(1, 5):
            start = cls.base + timedelta(minutes=30+g*20)
            entry = {
                "series_id": "synthetic-bo7-a", "game_number": g,
                "team_ids": ["synthetic-A", "synthetic-B"],
                "decision": "HOLD" if g == 3 else "FORECAST",
                "probability_a": None if g == 3 else 0.56,
                "reason_code": "NO_BP" if g == 3 else "SHADOW_FORECAST",
                "phase": "PRE_GAME",
                "info_cutoff_at": iso(cls.base-timedelta(seconds=1)),
                "forecast_at": iso(cls.base),
                "game_start_at": (iso(cls.base+timedelta(minutes=30))
                                  if g == 1 else iso(start)),
                "basis_source_id": "synthetic-source-only"
            }
            with patch("research.kpl_v20_shadow_trial._utcnow",
                       return_value=cls.base):
                submit_shadow_decision(cls.source, entry)
        cls.original_receipts = []
        for kind, sid, game in [
            ("MANIFEST", None, None),
            *[("DECISION", "synthetic-bo7-a", n) for n in range(1, 5)]
        ]:
            result = prepare_shadow_timestamp_request(
                cls.source, object_kind=kind, series_id=sid, game_number=game)
            if "request_b64" not in result:
                raise AssertionError(f"Cannot create RFC3161 request: {result}")
            req = base64.b64decode(result["request_b64"])
            query = certdir / "request.tsq"
            token = certdir / "timestamp.der"
            query.write_bytes(req)
            run("ts", "-reply", "-queryfile", str(query),
                "-signer", str(certdir/"tsa.pem"),
                "-inkey", str(certdir/"tsa.key"),
                "-chain", str(certdir/"root.pem"),
                "-tspolicy", "1.3.6.1.4.1.55555.22",
                "-out", str(token), "-token_out")
            cls.original_receipts.append({
                "object_kind": kind, "series_id": sid, "game_number": game,
                "request_b64": result["request_b64"],
                "token_b64": base64.b64encode(token.read_bytes()).decode()})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="kpl-v22-case-")
        self.addCleanup(self._temp.cleanup)
        self.dir = Path(self._temp.name) / "shadow"
        shutil.copytree(self.source, self.dir)
        self.receipts = copy.deepcopy(self.original_receipts)

    def audit(self, receipts=None, trust=None, **kw):
        return audit_shadow_timestamp_bundle(
            self.dir, self.receipts if receipts is None else receipts,
            self.trust if trust is None else trust, **kw)

    def test_matching_real_cryptographic_tokens_still_hold(self):
        r = self.audit()
        self.assertEqual(r["expected_record_count"], 5)
        self.assertEqual(r["cryptographically_consistent_record_count"], 5, r)
        self.assertTrue(r["all_manifest_and_recorded_decisions_timestamp_bound"])
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["independent_tsa_identity_verified"])
        self.assertFalse(r["registered_kpl_fixture_independently_verified"])
        self.assertFalse(r["real_kpl_accuracy_verified"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["live_execution_allowed"])
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertIn("REVOCATION_EVIDENCE_MISSING_OR_UNVERIFIED", r["reasons"])

    def test_forecast_and_hold_decisions_both_need_evidence(self):
        r = self.audit()
        self.assertEqual(
            {(x["object_kind"], x["game_number"]) for x in r["record_evidence"]},
            {("MANIFEST", None)} |
            {("DECISION", g) for g in range(1, 5)})

    def test_request_preparation_is_not_submission(self):
        r = prepare_shadow_timestamp_request(
            self.dir, object_kind="DECISION",
            series_id="synthetic-bo7-a", game_number=3)
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["sent_to_tsa"])
        self.assertIn("request_b64", r)
        self.assertFalse(r["external_time_source_independently_verified"])

    def test_omitted_manifest_timestamp_fails_coverage(self):
        r = self.audit(receipts=self.receipts[1:])
        self.assertIn("INCOMPLETE_TIMESTAMP_RECEIPT_COVERAGE", r["reasons"])
        self.assertFalse(r["all_manifest_and_recorded_decisions_timestamp_bound"])

    def test_omitted_forecast_timestamp_fails_coverage(self):
        r = self.audit(receipts=self.receipts[:-1])
        self.assertIn("INCOMPLETE_TIMESTAMP_RECEIPT_COVERAGE", r["reasons"])

    def test_duplicate_timestamp_receipt_rejected(self):
        r = self.audit(receipts=self.receipts[:-1] + [self.receipts[0]])
        self.assertIn("UNKNOWN_DUPLICATE_OR_CROSS_GAME_RECEIPT", r["reasons"])

    def test_cross_game_token_replay_rejected(self):
        copied = copy.deepcopy(self.receipts)
        copied[2]["token_b64"] = copied[1]["token_b64"]
        r = self.audit(receipts=copied)
        self.assertLess(r["cryptographically_consistent_record_count"], 5)
        self.assertIn("BAD_RFC3161_TOKEN_OR_SIGNER", r["reasons"])

    def test_nonce_replay_different_query_same_record_rejected(self):
        copied = copy.deepcopy(self.receipts)
        newly_generated = prepare_shadow_timestamp_request(
            self.dir, object_kind="DECISION",
            series_id="synthetic-bo7-a", game_number=1)
        copied[1]["request_b64"] = newly_generated["request_b64"]
        r = self.audit(receipts=copied)
        self.assertIn("TSA_NONCE_OR_REQUEST_IMPRINT_MISMATCH", r["reasons"])
        self.assertFalse(r["all_manifest_and_recorded_decisions_timestamp_bound"])

    def test_forged_extra_verified_flag_rejected(self):
        copied = copy.deepcopy(self.receipts)
        copied[1]["external_tsa_verified"] = True
        self.assertIn("INVALID_TIMESTAMP_RECEIPT_SCHEMA",
                      self.audit(receipts=copied)["reasons"])

    def test_corrupt_timestamp_token_base64_rejected(self):
        copied = copy.deepcopy(self.receipts)
        copied[1]["token_b64"] = "%%%notbase64"
        r = self.audit(receipts=copied)
        self.assertIn("INVALID_OR_UNVERIFIABLE_TIMESTAMP_RECEIPT",
                      r["reasons"])

    def test_deleted_middle_game_and_receipt_must_not_pass(self):
        # The original V20 registry recorded G1..G4. If an adversary
        # deletes G2 and its timestamp, the V22 auditor must not treat
        # the remaining 4 pieces as a fully witnessed trial.
        (self.dir / "decisions" / "synthetic-bo7-a-g2.json").unlink()
        survivors = [
            r for r in self.receipts
            if not (r["object_kind"] == "DECISION" and r["game_number"] == 2)
        ]
        result = self.audit(receipts=survivors)
        self.assertIn("INVALID_LOCAL_SHADOW_RECORDS", result["reasons"])
        self.assertFalse(result["all_manifest_and_recorded_decisions_timestamp_bound"])

    def test_modified_forecast_after_tsa_signing_rejected(self):
        path = self.dir / "decisions" / "synthetic-bo7-a-g1.json"
        obj = json.loads(path.read_text())
        obj["decision"]["probability_a"] = 0.99
        path.write_text(json.dumps(obj)+"\n")
        r = self.audit()
        self.assertIn("BAD_RFC3161_TOKEN_OR_SIGNER", r["reasons"])
        self.assertLess(r["cryptographically_consistent_record_count"], 5)

    def test_modified_manifest_after_signing_fails(self):
        path = self.dir / "manifest.json"
        obj = json.loads(path.read_text())
        obj["model_version"] = "fake-model-rewritten"
        path.write_text(json.dumps(obj)+"\n")
        r = self.audit()
        self.assertIn("INVALID_LOCAL_SHADOW_RECORDS", r["reasons"])

    def test_wrong_pinned_tsa_cert_rejected(self):
        changed = copy.deepcopy(self.trust)
        changed["tsa_cert_sha256"] = "f"*64
        r = self.audit(trust=changed)
        self.assertIn("PINNED_TSA_CERTIFICATE_MISMATCH", r["reasons"])

    def test_no_independently_pinned_tsa_rejected(self):
        r = self.audit(trust={})
        self.assertIn("INVALID_TSA_TRUST_CONFIG", r["reasons"])

    def test_manifest_only_not_a_complete_pregame_witness(self):
        for p in (self.dir/"decisions").iterdir():
            p.unlink()
        r = self.audit(receipts=self.receipts[:1])
        self.assertIn("NO_PREMAP_DECISIONS_REGISTERED", r["reasons"])

    def test_symlink_shadow_file_rejected(self):
        p = self.dir / "decisions" / "synthetic-bo7-a-g1.json"
        target = self.dir / "target.json"
        p.rename(target)
        p.symlink_to(target)
        r = self.audit()
        self.assertIn("INVALID_LOCAL_SHADOW_RECORDS", r["reasons"])

    def test_invalid_stamping_deadline_fails_closed(self):
        req = _decode_b64(self.receipts[1]["request_b64"], 8192)
        token = _decode_b64(self.receipts[1]["token_b64"], 128000)
        path = self.dir / "decisions" / "synthetic-bo7-a-g1.json"
        raw = path.read_bytes()
        error, ok, _ = _verify_req_token(
            req, token, raw, self.trust, None,
            self.base, self.base-timedelta(seconds=1))
        self.assertEqual(error, "TOKEN_GENERATED_OUTSIDE_PRE_GAME_WINDOW")
        self.assertFalse(ok)

    def test_missing_revocation_never_becomes_full_trust(self):
        r = self.audit()
        self.assertEqual(r["locally_checked_revocation_record_count"], 0)
        self.assertFalse(r["revocation_status_completely_authenticated"])
        self.assertFalse(r["trusted_root_independently_authenticated"])

    def test_wrong_event_series_identity_rejected(self):
        copied = copy.deepcopy(self.receipts)
        copied[1]["series_id"] = "synthetic-bo7-elsewhere"
        r = self.audit(receipts=copied)
        self.assertIn("UNKNOWN_DUPLICATE_OR_CROSS_GAME_RECEIPT", r["reasons"])

    def test_unknown_unregistered_decision_not_prepared(self):
        r = prepare_shadow_timestamp_request(
            self.dir, object_kind="DECISION",
            series_id="unknown", game_number=1)
        self.assertIn("UNKNOWN_OR_UNREGISTERED_SHADOW_RECORD", r["reasons"])


if __name__ == "__main__":
    unittest.main()
