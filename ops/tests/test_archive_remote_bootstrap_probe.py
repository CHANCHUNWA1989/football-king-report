"""Adversarial, no-network tests for the remote archive bootstrap probe."""

import contextlib
import io
import json
from unittest import mock
import unittest

from ops.archive_remote_bootstrap_probe import (
    ARCHIVE_REF, BOOTSTRAP_SHA, REPO_URL, RemoteBootstrapHold,
    check_remote_bootstrap, main, parse_ref_reply,
)


def advertisement(sha=BOOTSTRAP_SHA, ref=ARCHIVE_REF):
    return (sha + "\t" + ref + "\n").encode("ascii")


class ArchiveRemoteBootstrapProbeTests(unittest.TestCase):
    def test_exact_initial_remote_head_observed_without_release(self):
        record = parse_ref_reply(advertisement())
        self.assertEqual(record["archive_sha"], BOOTSTRAP_SHA)
        self.assertTrue(record["read_only_probe"])
        self.assertFalse(record["effective_branch_protection_verified"])
        self.assertFalse(record["remote_canary_write_verified"])
        self.assertFalse(record["independent_review_verified"])
        self.assertEqual(record["production_recommendations"], "DISABLED")

    def test_changed_remote_head_causes_hard_hold(self):
        with self.assertRaisesRegex(
                RemoteBootstrapHold, "REMOTE_ARCHIVE_REF_DRIFT_FROM_BOOTSTRAP"):
            parse_ref_reply(advertisement("f" * 40))

    def test_main_ref_is_not_archive_ref(self):
        with self.assertRaisesRegex(
                RemoteBootstrapHold, "UNTRUSTED_REMOTE_REF_ADVERTISEMENT"):
            parse_ref_reply(advertisement(ref="refs/heads/main"))

    def test_archive_name_substring_cannot_be_accepted(self):
        with self.assertRaisesRegex(
                RemoteBootstrapHold, "UNTRUSTED_REMOTE_REF_ADVERTISEMENT"):
            parse_ref_reply(advertisement(
                ref="refs/heads/research/forward-provenance-archive-evil"))

    def test_missing_and_duplicate_remote_advertisement_both_rejected(self):
        for raw in (b"", advertisement() * 2,
                    advertisement() + advertisement("f" * 40)):
            with self.subTest(length=len(raw)), self.assertRaises(RemoteBootstrapHold):
                parse_ref_reply(raw)

    def test_non_sha_blank_and_binary_rejected(self):
        for raw in (b"fake\t" + ARCHIVE_REF.encode() + b"\n",
                    b" \n", b"\xff\xfe\n", advertisement() + b"\x00"):
            with self.subTest(raw_len=len(raw)), self.assertRaises(RemoteBootstrapHold):
                parse_ref_reply(raw)

    def test_large_or_wrong_type_response_rejected(self):
        for raw in (b"x" * 2000, "not bytes", None):
            with self.subTest(type=str(type(raw))), self.assertRaises(RemoteBootstrapHold):
                parse_ref_reply(raw)

    def test_wrong_expected_sha_cannot_skip_check(self):
        with self.assertRaisesRegex(
                RemoteBootstrapHold, "INVALID_EXPECTED_ARCHIVE_SHA"):
            parse_ref_reply(advertisement(), "a" * 39)

    def test_public_probe_uses_only_one_exact_read_only_git_command(self):
        completed = mock.Mock(returncode=0, stdout=advertisement())
        with mock.patch("ops.archive_remote_bootstrap_probe.subprocess.run",
                        return_value=completed) as sub:
            record = check_remote_bootstrap()
        argv = sub.call_args.args[0]
        self.assertEqual(argv, [
            "git", "ls-remote", "--exit-code", "--heads",
            REPO_URL, ARCHIVE_REF])
        self.assertNotIn("push", argv)
        self.assertNotIn("fetch", argv)
        self.assertIsNone(sub.call_args.kwargs.get("input"))
        self.assertEqual(sub.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(record["archive_sha"], BOOTSTRAP_SHA)

    def test_transport_error_is_unknown_not_fabricated_drift(self):
        with mock.patch("ops.archive_remote_bootstrap_probe.subprocess.run",
                        return_value=mock.Mock(returncode=128, stdout=b"")):
            with self.assertRaisesRegex(
                    RemoteBootstrapHold, "REMOTE_REF_READ_UNAVAILABLE"):
                check_remote_bootstrap()

    def test_cli_on_unavailable_remote_outputs_only_bounded_hold(self):
        with mock.patch("ops.archive_remote_bootstrap_probe.check_remote_bootstrap",
                        side_effect=RemoteBootstrapHold("PRIVATE_TOKEN_VALUE")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["--read-only"])
        self.assertEqual(code, 1)
        content = json.loads(out.getvalue())
        self.assertEqual(content["status"],
                         "HOLD_REMOTE_ARCHIVE_BOOTSTRAP_NOT_CONFIRMED")
        self.assertEqual(content["production_recommendations"], "DISABLED")
        self.assertNotIn("PRIVATE_TOKEN_VALUE", out.getvalue())

    def test_no_implicit_probe_without_explicit_read_only_option(self):
        with self.assertRaises(SystemExit):
            main([])


if __name__ == "__main__":
    unittest.main()
