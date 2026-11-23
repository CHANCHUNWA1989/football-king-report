"""Offline adverse cases for a genuine read-only GitHub policy observation.

Neither ruleset existence nor successful GET provides a release permit.
"""

import contextlib
import io
import json
from unittest import mock
import unittest
from urllib import error

from ops.archive_remote_policy_probe import (
    CLASSIC_URL, HEADERS, RULES_URL, PolicyHold, _get, _summary, main, observe,
)


class ArchiveRemotePolicyProbeTests(unittest.TestCase):
    def test_no_active_rules_is_hold_not_protected(self):
        receipt = _summary(200, b"[]", 404, b"")
        self.assertEqual(receipt["status"],
                         "HOLD_POLICY_OBSERVATION_ONLY_NOT_AUTHORIZED")
        self.assertFalse(receipt["effective_non_fast_forward_rule_observed"])
        self.assertFalse(receipt["effective_deletion_rule_observed"])
        self.assertFalse(receipt["ruleset_activation_authorized"])
        self.assertFalse(receipt["classic_protection_fully_audited"])
        self.assertFalse(receipt["writer_identity_approved"])

    def test_both_rules_observed_is_still_hold_due_to_bypass_uncertainty(self):
        receipt = _summary(200, b'[{"type":"deletion"},{"type":"non_fast_forward"}]',
                           200, b'{"allow_force_pushes":{"enabled":false}}')
        self.assertTrue(receipt["effective_deletion_rule_observed"])
        self.assertTrue(receipt["effective_non_fast_forward_rule_observed"])
        self.assertFalse(receipt["ruleset_bypass_actors_audited"])
        self.assertFalse(receipt["reviewer_independent_approval"])
        self.assertFalse(receipt["ruleset_activation_authorized"])
        self.assertEqual(receipt["production_recommendations"], "DISABLED")

    def test_effective_rule_only_does_not_establish_classic_protection(self):
        receipt = _summary(200, b'[{"type":"deletion"}]', 404, b"")
        self.assertFalse(receipt["classic_protection_fully_audited"])
        self.assertFalse(receipt["effective_non_fast_forward_rule_observed"])

    def test_classic_200_only_is_not_evidence_for_active_ruleset(self):
        receipt = _summary(200, b"[]", 200, b'{"required_status_checks":null}')
        self.assertFalse(receipt["effective_non_fast_forward_rule_observed"])
        self.assertFalse(receipt["ruleset_activation_authorized"])

    def test_rules_endpoint_403_is_unknown_never_false_or_ready(self):
        receipt = _summary(403, b"", 404, b"")
        self.assertEqual(receipt["status"], "HOLD_POLICY_NOT_COMPLETELY_OBSERVED")
        self.assertFalse(receipt["rules_response_complete"])
        self.assertFalse(receipt["ruleset_activation_authorized"])

    def test_classic_401_and_rate_limit_429_fail_closed(self):
        for code in (401, 403, 429, 500, 503):
            with self.subTest(code=code):
                result = _summary(200, b"[]", code, b"")
                self.assertEqual(result["status"],
                                 "HOLD_POLICY_NOT_COMPLETELY_OBSERVED")
                self.assertFalse(result["ruleset_activation_authorized"])

    def test_100_rules_page_must_not_be_treated_complete(self):
        body = json.dumps([{"type": "deletion"}] * 100).encode()
        result = _summary(200, body, 404, b"")
        self.assertFalse(result["rules_response_complete"])
        self.assertEqual(result["status"],
                         "HOLD_POLICY_NOT_COMPLETELY_OBSERVED")

    def test_json_duplicate_keys_and_nan_rejected(self):
        for raw in (b'[{"type":"deletion","type":"non_fast_forward"}]',
                    b'[{"type":NaN}]'):
            with self.subTest(raw=raw), self.assertRaises(PolicyHold):
                _summary(200, raw, 404, b"")

    def test_unexpected_rules_shape_or_classic_shape_rejected(self):
        for raw in (b"{}", b'["deletion"]', b'[{"oops":"missing_type"}]',
                    b"null", b"[] trailing"):
            with self.subTest(raw=raw), self.assertRaises(PolicyHold):
                _summary(200, raw, 404, b"")
        with self.assertRaises(PolicyHold):
            _summary(200, b"[]", 200, b"[]")

    def test_bounded_document_refuses_oversized_output(self):
        with self.assertRaises(PolicyHold):
            _summary(200, b"a" * 150000, 404, b"")

    def test_unexpected_http_status_cannot_be_reported(self):
        with self.assertRaisesRegex(PolicyHold, "UNEXPECTED_POLICY_HTTP_STATUS"):
            _summary(301, b"", 200, b"{}")

    def test_fixed_allowlisted_urls_only(self):
        with self.assertRaisesRegex(PolicyHold, "POLICY_URL_NOT_ALLOWLISTED"):
            _get("https://evil.invalid/authorization")
        self.assertEqual(HEADERS["Accept"], "application/vnd.github+json")
        self.assertNotIn("Authorization", HEADERS)

    def test_get_uses_get_only_and_fixed_bounded_read(self):
        response = mock.MagicMock()
        response.status = 200
        response.read.return_value = b"[]"
        opener = mock.MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with mock.patch(
                "ops.archive_remote_policy_probe.request.build_opener",
                return_value=opener) as b:
            code, body = _get(RULES_URL)
        self.assertEqual((code, body), (200, b"[]"))
        req = opener.open.call_args.args[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.full_url, RULES_URL)
        self.assertEqual(response.read.call_args.args[0], 131073)
        self.assertEqual(len(b.call_args.args), 1)

    def test_404_http_error_is_observed_without_raw_body(self):
        failure = error.HTTPError(CLASSIC_URL, 404, "SECRET_VALUE", None, None)
        opener = mock.MagicMock()
        opener.open.side_effect = failure
        with mock.patch(
                "ops.archive_remote_policy_probe.request.build_opener",
                return_value=opener):
            code, body = _get(CLASSIC_URL)
        self.assertEqual((code, body), (404, b""))

    def test_network_failure_does_not_leak_error(self):
        with mock.patch("ops.archive_remote_policy_probe._get",
                        side_effect=PolicyHold("PRIVATE_CREDENTIAL")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["--observe-only"])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(buf.getvalue())["status"],
                         "HOLD_REMOTE_BRANCH_POLICY_NOT_VERIFIABLE")
        self.assertNotIn("PRIVATE_CREDENTIAL", buf.getvalue())

    def test_observe_contacts_both_fixed_endpoints_once(self):
        with mock.patch("ops.archive_remote_policy_probe._get",
                        side_effect=[(200, b"[]"), (404, b"")]) as getter:
            report = observe()
        self.assertEqual([c.args[0] for c in getter.call_args_list],
                         [RULES_URL, CLASSIC_URL])
        self.assertFalse(report["ruleset_activation_authorized"])

    def test_cli_observation_green_does_not_authorize_any_write(self):
        with mock.patch("ops.archive_remote_policy_probe.observe",
                        return_value=_summary(200, b"[]", 404, b"")):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--observe-only"])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertFalse(report["ruleset_activation_authorized"])
        self.assertFalse(report["remote_synthetic_canary_write_verified"])
        self.assertEqual(report["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
