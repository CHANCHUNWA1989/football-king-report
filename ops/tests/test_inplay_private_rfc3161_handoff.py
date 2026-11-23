"""No real TSA or bookmaker inputs. Tests inject mocked OpenSSL results."""
import copy
import io
import json
import re
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_private_rfc3161_handoff import make_query, verify_response, TimestampHandoffError
from test_inplay_forward_private_seal import input_case
from inplay_forward_private_seal import seal_candidate


STAMP = "Time stamp: Nov 23 05:30:40 2026 GMT"


def runner_good(commands):
    def runner(cmd, **kwargs):
        commands.append(cmd)
        if "-query" in cmd:
            return SimpleNamespace(returncode=0, stdout=b"synthetic-tsq-only")
        if "-reply" in cmd:
            return SimpleNamespace(returncode=0, stdout=STAMP, stderr="")
        return SimpleNamespace(returncode=0, stdout="Verification: OK", stderr="")
    return runner


def fixture(directory):
    private = Path(directory) / "private"
    private.mkdir()
    r = seal_candidate(**input_case(), destination=private)
    archive = Path(r["private_archive"])
    query = private / "candidate.tsq"
    token = private / "reply.tsr"
    ca = private / "trusted-ca.pem"
    token.write_bytes(b"synthetic-untrusted-token")
    ca.write_bytes(b"synthetic-test-root-not-real-ca")
    return archive, query, token, ca


class TimestampHandoffTests(unittest.TestCase):
    def test_request_is_digest_only_and_does_not_publish_raw(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            calls = []
            result = make_query(archive, query, runner=runner_good(calls))
            self.assertEqual(result["status"], "RESEARCH_ONLY")
            self.assertEqual(result["decision"], "HOLD")
            self.assertTrue(result["request_contains_only_archive_digest"])
            self.assertEqual(query.read_bytes(), b"synthetic-tsq-only")
            self.assertEqual(query.stat().st_mode & 0o777, 0o600)
            self.assertEqual(calls[0][:3], ["openssl", "ts", "-query"])
            self.assertIn("-digest", calls[0])
            self.assertNotIn(str(archive), calls[0])
            self.assertEqual(len(calls[0][calls[0].index("-digest")+1]), 64)

    def test_valid_mock_is_not_full_external_certification(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            calls=[]
            make_query(archive, query, runner=runner_good(calls))
            result=verify_response(archive, query, token, ca, runner=runner_good(calls))
            self.assertEqual(result["status"], "RESEARCH_ONLY")
            self.assertTrue(result["cryptographic_imprint_check_passed"])
            self.assertFalse(result["issuer_policy_independently_approved"])
            self.assertFalse(result["independently_timestamped"])
            self.assertFalse(result["positive_ev_verified"])
            self.assertEqual(result["decision"], "HOLD")
            self.assertEqual(result["certified_forward_samples"], 0)
            verify_calls=[x for x in calls if "-verify" in x]
            self.assertEqual(len(verify_calls), 2)
            self.assertIn("-digest", verify_calls[0])
            self.assertIn("-queryfile", verify_calls[1])

    def test_query_creation_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, _, _ = fixture(d)
            make_query(archive, query, runner=runner_good([]))
            with self.assertRaisesRegex(TimestampHandoffError, "UNSAFE_OR_EXISTING_QUERY_DESTINATION"):
                make_query(archive, query, runner=runner_good([]))

    def test_tampered_archive_fails_even_if_receipt_claims_old_sha(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            archive.write_bytes(archive.read_bytes() + b"attack")
            self.assertEqual(verify_response(archive, query, token, ca, runner=runner_good([]))["status"], "HOLD")

    def test_wrong_archive_filename_hash_holds(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            renamed = archive.with_name("candidate-20261123T053000Z-" + "a"*16 + ".tar")
            archive.rename(renamed)
            self.assertEqual(verify_response(renamed, query, token, ca, runner=runner_good([]))["reason"],
                             "ARCHIVE_FILENAME_DIGEST_CONFLICT")

    def test_mismatched_query_nonce_holds(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            query.write_bytes(b"unrelated request")
            calls=[]
            def fail_nonce(cmd, **kwargs):
                calls.append(cmd)
                return SimpleNamespace(returncode=1 if "-queryfile" in cmd else 0,
                                       stdout=STAMP, stderr="")
            result=verify_response(archive, query, token, ca, runner=fail_nonce)
            self.assertEqual(result["status"], "HOLD")
            self.assertFalse(result["cryptographic_imprint_check_passed"])
            self.assertEqual(len(calls), 2)

    def test_bad_signature_or_imprint_holds(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            def fail_first(cmd, **kwargs):
                return SimpleNamespace(returncode=1, stdout="", stderr="synthetic failure")
            self.assertEqual(verify_response(archive, query, token, ca, runner=fail_first)["status"], "HOLD")

    def test_replayed_late_token_holds(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            def late(cmd, **kwargs):
                return SimpleNamespace(returncode=0,
                    stdout=("Time stamp: Nov 23 06:02:00 2026 GMT" if "-reply" in cmd
                            else "Verification: OK"), stderr="")
            self.assertEqual(verify_response(archive, query, token, ca, runner=late)["reason"],
                             "TSA_TIME_NOT_TIMELY_FOR_THIS_CAPTURE")

    def test_before_capture_window_holds(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            def early(cmd, **kwargs):
                return SimpleNamespace(returncode=0,
                    stdout="Time stamp: Nov 23 05:28:00 2026 GMT", stderr="")
            self.assertEqual(verify_response(archive, query, token, ca, runner=early)["status"], "HOLD")

    def test_bad_or_ambiguous_stamp_text_holds(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            for stamp in ("Time stamp: invalid", STAMP+"\n"+STAMP):
                def bad(cmd, **kwargs):
                    return SimpleNamespace(returncode=0, stdout=stamp, stderr="")
                self.assertEqual(verify_response(archive, query, token, ca, runner=bad)["reason"],
                                 "UNRECOGNIZED_TSA_TIME")

    def test_missing_ca_and_symlink_token_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            ca.unlink()
            self.assertEqual(verify_response(archive, query, token, ca, runner=runner_good([]))["status"], "HOLD")
            ca.write_bytes(b"synthetic")
            token2 = token.with_name("symlink.tsr")
            token2.symlink_to(token)
            self.assertEqual(verify_response(archive, query, token2, ca, runner=runner_good([]))["status"], "HOLD")

    def test_rejected_raw_file_digest_inside_archive(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            # Repack a semantically tampered raw item while updating the filename to
            # avoid rejecting for the unrelated outer file-name digest first.
            files = {}
            with tarfile.open(archive, "r") as original:
                for member in original.getmembers():
                    files[member.name]=original.extractfile(member).read()
            files["quote.raw"]=b"changed quotation"
            buf=io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as out:
                for name, raw in files.items():
                    m=tarfile.TarInfo(name)
                    m.size=len(raw);m.uid=m.gid=m.mtime=0;m.mode=0o600
                    out.addfile(m,io.BytesIO(raw))
            import hashlib
            digest=hashlib.sha256(buf.getvalue()).hexdigest()
            renamed=archive.with_name("candidate-20261123T053000Z-"+digest[:16]+".tar")
            renamed.write_bytes(buf.getvalue())
            self.assertEqual(verify_response(renamed, query, token, ca, runner=runner_good([]))["reason"],
                             "TAMPERED_RAW_SUBJECT")

    def test_no_publisher_approval_implied_from_mocked_success(self):
        with tempfile.TemporaryDirectory() as d:
            archive, query, token, ca = fixture(d)
            r=verify_response(archive, query, token, ca, runner=runner_good([]))
            for key in ("issuer_policy_independently_approved",
                        "provider_data_authenticated", "live_market_executable_verified",
                        "positive_ev_verified", "model_scoring_eligible"):
                self.assertFalse(r[key])
            self.assertIsNone(r["recommendation"])


if __name__ == "__main__":
    unittest.main()
