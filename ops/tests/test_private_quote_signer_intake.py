"""Synthetic manual signer intake policy tests; never call live Sigstore or odds API."""
import base64
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_private_quote_forward_freeze import inputs, encode
from private_quote_forward_freeze import freeze
from private_quote_signer_intake import (
    IntakeError, decode_dispatch_seal, validate_sanitized_seal, main,
    MAX_SAFE_BYTES,
)

CLOCK = datetime(2026, 11, 2, 5, 4, tzinfo=timezone.utc)


def local_safe_seal():
    raw, receipt, fixture, market, forecast = inputs()
    seal = freeze(raw, receipt, fixture, market, encode(forecast))
    blob = (json.dumps(seal, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    return seal, blob, digest


class ManualSafeSignerIntakeTests(unittest.TestCase):
    def test_valid_exact_bytes_pass_without_promoting_model_or_authenticating_quotes(self):
        seal, blob, digest = local_safe_seal()
        self.assertEqual(validate_sanitized_seal(blob, expected_sha256=digest, now=CLOCK), blob)
        b64 = base64.b64encode(blob).decode("ascii")
        self.assertEqual(decode_dispatch_seal(b64, expected_sha256=digest, now=CLOCK), blob)
        self.assertFalse(seal["forecast_was_witnessed_before_kickoff"])
        self.assertFalse(seal["bookmaker_quote_independently_authenticated"])
        self.assertEqual(seal["eligible_independently_verified_forward_samples"], 0)
        self.assertLess(len(blob), MAX_SAFE_BYTES)
        for private in (b"Private Home", b"Private Away", b"private-native-event-1",
                        b"synthetic-private-book", b"1.9183", b"1.9587",
                        b"score_distribution", b"model_version"):
            self.assertNotIn(private, blob)

    def test_mutating_any_byte_invalidates_dispatch_digest(self):
        _, blob, digest = local_safe_seal()
        for changed in (blob + b" ", blob.replace(b'"status":"RESEARCH_ONLY"', b'"status":"RESEARCH_ONLY" ')):
            with self.subTest(tail=changed[-9:]):
                with self.assertRaisesRegex(IntakeError, "SEAL_BYTES_DIGEST_MISMATCH"):
                    validate_sanitized_seal(changed, expected_sha256=digest, now=CLOCK)

    def test_unknown_raw_odds_or_real_identifier_fields_rejected_even_with_new_sha(self):
        seal, _, _ = local_safe_seal()
        for badfield, value in (
            ("bookmakers", [{"price": 1.91}]),
            ("provider_event_id", "private-event"),
            ("home_team", "Private Home"),
            ("source_response", {"odds": [1.91, 1.93]}),
            ("score_distribution", [[0, 0, 1.0]]),
            ("api_key", "private-credential"),
            ("independently_verified", True),
        ):
            with self.subTest(field=badfield):
                bad = dict(seal, **{badfield: value})
                blob = json.dumps(bad).encode()
                with self.assertRaisesRegex(IntakeError, "UNSAFE_SEAL_FIELDS"):
                    validate_sanitized_seal(blob, expected_sha256=hashlib.sha256(blob).hexdigest(),
                                            now=CLOCK)

    def test_credential_or_betting_claim_cannot_pass_signer(self):
        seal, _, _ = local_safe_seal()
        for field, value in (
            ("production_recommendations", "ENABLED"),
            ("status", "APPROVED"),
            ("can_publish_pick", True),
            ("bookmaker_quote_independently_authenticated", True),
            ("score_distribution_calibration_verified", True),
            ("fixture_source_independently_authenticated", True),
            ("forecast_was_witnessed_before_kickoff", True),
            ("eligible_independently_verified_forward_samples", 300),
            ("eligible_for_model_scoring", True),
            ("raw_snapshot_binding_replayed", False),
            ("score_distribution_structurally_normalized", False),
        ):
            with self.subTest(field=field):
                forged = deepcopy(seal)
                forged[field] = value
                # Recompute the local checksum: being self-consistent is not proof!
                unsigned = {k: v for k, v in forged.items() if k != "seal_sha256_unanchored"}
                forged["seal_sha256_unanchored"] = hashlib.sha256(
                    json.dumps(unsigned, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode()).hexdigest()
                blob = json.dumps(forged).encode()
                with self.assertRaises(IntakeError):
                    validate_sanitized_seal(blob, expected_sha256=hashlib.sha256(blob).hexdigest(),
                                            now=CLOCK)

    def test_forged_local_seal_checksum_rejected(self):
        seal, _, _ = local_safe_seal()
        seal["forecast_raw_byte_count"] += 1
        blob = json.dumps(seal).encode()
        with self.assertRaisesRegex(IntakeError, "LOCAL_SEAL_CHECKSUM_MISMATCH"):
            validate_sanitized_seal(blob, expected_sha256=hashlib.sha256(blob).hexdigest(),
                                    now=CLOCK)

    def test_noncanonical_or_invalid_clocks_rejected(self):
        for field, value in (
            ("training_cutoff_utc_claimed", "2026-11-03T00:00:00+00:00"),
            ("prediction_utc_claimed", "2026-11-02T07:51:00+00:00"),
            ("prediction_utc_claimed", "2026-11-02T05:01:00"),
            ("prediction_utc_claimed", "2026-11-02T13:01:00+08:00"),
            ("kickoff_utc_claimed", "bad-time"),
        ):
            with self.subTest(field=field):
                seal, _, _ = local_safe_seal()
                seal[field] = value
                unsigned = {k: v for k, v in seal.items() if k != "seal_sha256_unanchored"}
                seal["seal_sha256_unanchored"] = hashlib.sha256(json.dumps(
                    unsigned, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest()
                blob = json.dumps(seal).encode()
                with self.assertRaises(IntakeError):
                    validate_sanitized_seal(blob, expected_sha256=hashlib.sha256(blob).hexdigest(),
                                            now=CLOCK)

    def test_signer_refuses_when_workflow_starts_too_late_or_before_claim(self):
        _, blob, digest = local_safe_seal()
        for clock, reason in (
            (datetime(2026, 11, 2, 5, 0, tzinfo=timezone.utc),
             "FUTURE_OR_LEAKY_PREDICTION_CLAIM"),
            (datetime(2026, 11, 2, 7, 40, tzinfo=timezone.utc),
             "SIGNER_STARTED_TOO_LATE"),
            (datetime(2026, 11, 2, 7, 51, tzinfo=timezone.utc),
             "SIGNER_STARTED_TOO_LATE"),
        ):
            with self.subTest(clock=clock):
                with self.assertRaisesRegex(IntakeError, reason):
                    validate_sanitized_seal(blob, expected_sha256=digest, now=clock)
        with self.assertRaisesRegex(IntakeError, "INVALID_SIGNER_CLOCK"):
            validate_sanitized_seal(blob, expected_sha256=digest,
                                    now=datetime(2026, 11, 2, 5, 4))

    def test_base64_invalid_and_payload_size_guard(self):
        _, blob, digest = local_safe_seal()
        for bad in ("", "!!!!", "abc", "*"*15000, "\N{SNOWMAN}", 12, None):
            with self.subTest(bad=repr(bad)[:32]):
                with self.assertRaises(IntakeError):
                    decode_dispatch_seal(bad, expected_sha256=digest, now=CLOCK)
        for bad in (b"", b"x"*(MAX_SAFE_BYTES+1), "plain-text", bytearray(blob)):
            with self.assertRaises(IntakeError):
                validate_sanitized_seal(bad, expected_sha256=digest, now=CLOCK)
        with self.assertRaises(IntakeError):
            validate_sanitized_seal(blob, expected_sha256="!"*64, now=CLOCK)

    def test_duplicate_json_keys_nan_and_malformed_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"score":NaN}',
                    b'{"score":Infinity}', b'garbage', b'[]', b'\xff'):
            with self.subTest(raw=raw):
                with self.assertRaises(IntakeError):
                    validate_sanitized_seal(raw,
                                            expected_sha256=hashlib.sha256(raw).hexdigest(),
                                            now=CLOCK)

    def test_cli_exact_preserved_bytes_owner_only_output_and_no_overwrite(self):
        _, blob, digest = local_safe_seal()

        class FrozenClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 2, 5, 4, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as dirname:
            target = Path(dirname)/"seal.json"
            environ = {"SANITIZED_SEAL_BASE64": base64.b64encode(blob).decode("ascii"),
                       "EXPECTED_SEAL_SHA256": digest}
            with patch.dict(os.environ, environ):
                with patch("private_quote_signer_intake.datetime", FrozenClock):
                    with redirect_stdout(io.StringIO()) as output:
                        rc = main(["--output", str(target)])
            self.assertEqual(rc, 0, output.getvalue())
            self.assertEqual(target.read_bytes(), blob)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertNotIn("raw_snapshot_sha256", output.getvalue())
            self.assertNotIn(digest, output.getvalue())
            with patch.dict(os.environ, environ):
                with patch("private_quote_signer_intake.datetime", FrozenClock):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(main(["--output", str(target)]), 1)
            self.assertEqual(target.read_bytes(), blob)

    def test_signer_workflow_only_manual_main_nonexecuted_in_pr_ci(self):
        path = Path(__file__).resolve().parents[2] / ".github/workflows/football-king-private-seal-attest.yml"
        source = path.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", source)
        for automatic in ("\n  push:", "\n  pull_request:", "\n  schedule:",
                          "\n  workflow_run:", "\n  repository_dispatch:"):
            self.assertNotIn(automatic, source)
        self.assertIn("github.ref == 'refs/heads/main'", source)
        self.assertIn("inputs.acknowledge_public_metadata == true", source)
        self.assertIn("id-token: write", source)
        self.assertIn("attestations: write", source)
        self.assertIn("artifact-metadata: write", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("subject-path:", source)
        self.assertIn("actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6", source)
        self.assertIn("python ops/private_quote_signer_intake.py", source)
        self.assertNotIn("upload-artifact@", source)
        self.assertNotIn("pages: write", source)
        self.assertNotIn("secrets.", source)
        self.assertNotIn("THE_ODDS_API_KEY", source)


if __name__ == "__main__":
    unittest.main()
