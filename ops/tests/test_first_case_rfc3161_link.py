"""No-network adversarial test of the first-case RFC3161 byte-binding bridge.

Mocked OpenSSL success is only local control-flow testing, NOT a real TSA
token, and must never become a certified sports match or positive EV.
"""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from first_case_rfc3161_link import check


def encoded(v):
    return (json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def bundle():
    forecast = {
        "schema": "football-king-first-case-forecast-v1",
        "fixture_id": "synthetic-fixture-1", "league": "bundesliga",
        "home_key": "synthetic-home", "away_key": "synthetic-away",
        "kickoff_utc": "2026-11-21T12:00:00Z",
        "captured_utc": "2026-11-21T10:01:00Z",
        "model_version": "test-model", "probabilities_1x2": [.5, .25, .25],
        "production_recommendations": "DISABLED",
    }
    quote = {
        "schema": "football-king-first-case-quote-v1",
        "fixture_id": "synthetic-fixture-1", "league": "bundesliga",
        "home_key": "synthetic-home", "away_key": "synthetic-away",
        "kickoff_utc": "2026-11-21T12:00:00Z",
        "provider": "synthetic-provider", "provider_event_id": "synthetic-native-1",
        "market": "spreads", "selection": "HOME", "line": -.25,
        "observed_utc": "2026-11-21T10:00:00Z",
        "captured_utc": "2026-11-21T10:00:30Z",
        "decimal_odds": 1.943,
        "production_recommendations": "DISABLED",
    }
    raw_f, raw_q = encoded(forecast), encoded(quote)
    manifest = {
        "schema": "football-king-first-case-manifest-v1",
        "fixture_id": forecast["fixture_id"],
        "kickoff_utc": forecast["kickoff_utc"],
        "forecast_sha256": hashlib.sha256(raw_f).hexdigest(),
        "quote_sha256": hashlib.sha256(raw_q).hexdigest(),
        "created_utc": "2026-11-21T10:02:00Z",
        "status": "HOLD", "production_recommendations": "DISABLED",
    }
    return raw_f, raw_q, encoded(manifest)


class FirstCaseRFC3161LinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.token = root/"stamp.tsr"
        self.ca = root/"reviewed-ca.pem"
        self.token.write_bytes(b"FAKE-TOKEN-NOT-TRUSTWORTHY")
        self.ca.write_bytes(b"FAKE-CA-NOT-TRUSTWORTHY")
        self.inputs = bundle()

    def fake(self, *, verified=True, when="Nov 21 10:03:00 2026 GMT",
             description_ok=True, digest=None):
        calls = []
        def runner(cmd, **kwargs):
            calls.append(cmd)
            self.assertEqual(kwargs, {
                "capture_output": True, "text": True, "timeout": 20,
                "check": False,
            })
            if "-verify" in cmd:
                if digest is not None and cmd[cmd.index("-digest")+1] != digest:
                    return SimpleNamespace(returncode=1, stdout="", stderr="")
                return SimpleNamespace(returncode=0 if verified else 1,
                                       stdout="", stderr="")
            return SimpleNamespace(returncode=0 if description_ok else 1,
                                   stdout="Time stamp: " + when + "\n", stderr="")
        return runner, calls

    def call(self, runner, inputs=None, **changes):
        f, q, m = self.inputs if inputs is None else inputs
        return check(f, q, m, token_path=changes.get("token", self.token),
                     ca_path=changes.get("ca", self.ca), runner=runner)

    def test_valid_mock_uses_exact_manifest_digest_and_always_hold(self):
        fake, calls = self.fake()
        result = self.call(fake)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][:3], ["openssl", "ts", "-verify"])
        self.assertEqual(calls[0][calls[0].index("-digest")+1],
                         hashlib.sha256(self.inputs[2]).hexdigest())
        self.assertNotIn("-data", calls[0])
        self.assertTrue(result["byte_digest_binding_checked"])
        self.assertTrue(result["local_openssl_signature_and_imprint_checked"])
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["tsa_trust_policy_verified"])
        self.assertFalse(result["forecast_capture_time_independently_authenticated"])
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertEqual(result["certified_forward_case_count"], 0)
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertNotIn("decimal_odds", result)
        self.assertNotIn("probabilities_1x2", result)

    def test_changed_forecast_or_quote_without_repin_never_calls_openssl(self):
        f, q, m = self.inputs
        for altered in (
            (f.replace(b"test-model", b"test-model-changed"), q, m),
            (f, q.replace(b"1.943", b"1.944"), m),
            (f, q, m.replace(b"synthetic-fixture-1", b"other-fixture-0001")),
        ):
            fake, calls = self.fake()
            result = self.call(fake, inputs=altered)
            self.assertFalse(result["byte_digest_binding_checked"])
            self.assertFalse(result["local_openssl_signature_and_imprint_checked"])
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(len(calls), 0)

    def test_rehashed_manifest_still_requires_matching_real_token_imprint(self):
        f, q, old_manifest = self.inputs
        originally_pinned = hashlib.sha256(old_manifest).hexdigest()
        modified = json.loads(old_manifest)
        # Move within the valid 120-second freshness window: this change
        # must reach OpenSSL and be rejected by the old token imprint, rather
        # than failing the earlier quote-expiry gate.
        modified["created_utc"] = "2026-11-21T10:01:59Z"
        repinned_manifest = encoded(modified)
        fake, calls = self.fake(digest=originally_pinned)
        result = self.call(fake, inputs=(f,q,repinned_manifest))
        self.assertTrue(result["byte_digest_binding_checked"])
        self.assertFalse(result["local_openssl_signature_and_imprint_checked"])
        self.assertEqual(result["reason"], "TSA_SIGNATURE_OR_MANIFEST_IMPRINT_UNTRUSTED")
        self.assertEqual(calls[0][calls[0].index("-digest")+1],
                         hashlib.sha256(repinned_manifest).hexdigest())

    def test_bad_openssl_signature_and_description_hold(self):
        for args in ({"verified": False}, {"description_ok": False}):
            fake, _ = self.fake(**args)
            result = self.call(fake)
            self.assertFalse(result["local_openssl_signature_and_imprint_checked"])
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["certified_forward_case_count"], 0)

    def test_timestamp_before_declared_manifest_or_after_buffer_refused(self):
        for stamp, expected in (
            ("Nov 21 10:01:59 2026 GMT", "TOKEN_PREDATES_DECLARED_MANIFEST"),
            ("Nov 21 11:51:00 2026 GMT", "TOKEN_NOT_SAFELY_BEFORE_KICKOFF"),
        ):
            fake, _ = self.fake(when=stamp)
            with self.subTest(stamp=stamp):
                result = self.call(fake)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], expected)
                self.assertFalse(result["local_openssl_signature_and_imprint_checked"])

    def test_unrecognized_or_duplicate_token_timestamp_refused(self):
        for stamp in ("invalid", "Nov 21 10:03:00 2026 UTC",
                      "Nov 21 10:03:00 2026 GMT\nTime stamp: Nov 21 10:04:00 2026 GMT"):
            fake, _ = self.fake(when=stamp)
            result = self.call(fake)
            self.assertEqual(result["reason"], "UNRECOGNIZED_TIMESTAMP_FORMAT")

    def test_both_openssl_calls_use_private_same_pinned_token_bytes(self):
        seen = []
        def runner(cmd, **kwargs):
            token_path = Path(cmd[cmd.index("-in") + 1])
            self.assertNotEqual(token_path, self.token)
            self.assertTrue(token_path.is_file())
            self.assertEqual(token_path.read_bytes(), self.token.read_bytes())
            if "-verify" in cmd:
                ca_path = Path(cmd[cmd.index("-CAfile") + 1])
                self.assertNotEqual(ca_path, self.ca)
                self.assertEqual(ca_path.read_bytes(), self.ca.read_bytes())
                seen.append(token_path)
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            seen.append(token_path)
            return SimpleNamespace(returncode=0,
                                   stdout="Time stamp: Nov 21 10:03:00 2026 GMT\n",
                                   stderr="")
        r = self.call(runner)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0], seen[1])
        self.assertFalse(seen[0].exists())
        self.assertTrue(r["local_openssl_signature_and_imprint_checked"])
        self.assertFalse(r["tsa_trust_policy_verified"])
        self.assertEqual(r["certified_forward_case_count"], 0)

    def test_staged_token_tampering_between_openssl_calls_rejected(self):
        def runner(cmd, **kwargs):
            if "-verify" in cmd:
                Path(cmd[cmd.index("-in")+1]).write_bytes(b"swapped-token")
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            return SimpleNamespace(returncode=0,
                                   stdout="Time stamp: Nov 21 10:03:00 2026 GMT\n",
                                   stderr="")
        r = self.call(runner)
        self.assertEqual(r["reason"], "STAGED_TSA_INPUT_CHANGED")
        self.assertFalse(r["local_openssl_signature_and_imprint_checked"])
        self.assertEqual(r["status"], "HOLD")


    def test_missing_ca_and_symlink_token_prevent_runner_call(self):
        self.ca.unlink()
        fake, calls = self.fake()
        result = self.call(fake)
        self.assertEqual(result["reason"], "MISSING_OR_UNSAFE_TSA_INPUT")
        self.assertEqual(len(calls), 0)
        self.ca.write_bytes(b"FAKE-CA")
        self.token.unlink()
        self.token.symlink_to(self.ca)
        result = self.call(fake)
        self.assertEqual(result["reason"], "MISSING_OR_UNSAFE_TSA_INPUT")
        self.assertEqual(len(calls), 0)

    def test_same_token_as_ca_path_refused(self):
        fake, calls = self.fake()
        result = self.call(fake, token=self.ca)
        self.assertEqual(result["reason"], "TSA_TOKEN_AND_CA_MUST_DIFFER")
        self.assertEqual(len(calls), 0)


if __name__ == "__main__":
    unittest.main()
