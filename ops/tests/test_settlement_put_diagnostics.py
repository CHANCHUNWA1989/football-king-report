"""Offline negative controls for redacted GitHub Contents PUT status capture."""

import json
import unittest

from ops.settlement_put_diagnostics import inspect


class SettlementPutDiagnosticTests(unittest.TestCase):
    def test_201_created_and_zero_exit_only_combination_success(self):
        record = inspect(b"HTTP/2.0 201 Created\r\n", 0)
        self.assertEqual(record["http_status"], 201)
        self.assertEqual(record["classification"], "HTTP_2XX_RESPONSE")
        self.assertIs(record["contents_write_succeeded"], True)
        self.assertIs(record["retry_root_cause_verified"], False)

    def test_200_and_zero_exit_is_success_observation_only(self):
        record = inspect(b"HTTP/1.1 200 OK\r\n", 0)
        self.assertTrue(record["contents_write_succeeded"])
        self.assertFalse(record["retry_root_cause_verified"])

    def test_403_is_permission_or_branch_rule_uncertain(self):
        record = inspect(b"HTTP/2.0 403 Forbidden\r\n", 1)
        self.assertEqual(record["classification"],
                         "FORBIDDEN_PERMISSIONS_OR_BRANCH_RULE_UNVERIFIED")
        self.assertFalse(record["contents_write_succeeded"])

    def test_409_is_unverified_conflict_not_claimed_root(self):
        record = inspect(b"HTTP/2 409 Conflict\n", 1)
        self.assertEqual(record["classification"],
                         "CONFLICT_STALE_SHA_OR_CONCURRENT_WRITE_UNVERIFIED")
        self.assertFalse(record["retry_root_cause_verified"])

    def test_422_is_validation_or_policy_not_certain(self):
        record = inspect(b"HTTP/2.0 422 Unprocessable Entity\n", 1)
        self.assertEqual(record["classification"],
                         "VALIDATION_OR_REPOSITORY_POLICY_UNVERIFIED")
        self.assertFalse(record["contents_write_succeeded"])

    def test_401_and_404_are_distinguished(self):
        self.assertEqual(inspect(b"HTTP/2.0 401 Unauthorized\n", 1)["classification"],
                         "AUTHENTICATION_REQUIRED_OR_EXPIRED")
        self.assertEqual(inspect(b"HTTP/2.0 404 Not Found\n", 1)["classification"],
                         "RESOURCE_NOT_FOUND")

    def test_429_and_5xx_are_not_silently_retried_as_conflict(self):
        self.assertEqual(inspect(b"HTTP/2.0 429 Too Many Requests\n", 1)
                         ["classification"], "RATE_LIMITED")
        self.assertEqual(inspect(b"HTTP/2.0 503 Service Unavailable\n", 1)
                         ["classification"], "REMOTE_SERVER_ERROR")

    def test_missing_header_from_old_suppressed_logs_is_unknown(self):
        result = inspect(b"", 1)
        self.assertIsNone(result["http_status"])
        self.assertEqual(result["classification"], "HTTP_STATUS_NOT_CAPTURED")
        self.assertFalse(result["contents_write_succeeded"])

    def test_non_http_exception_is_not_invented_http_status(self):
        result = inspect(b"GraphQL error: Cannot access resource\n", 1)
        self.assertIsNone(result["http_status"])
        self.assertFalse(result["retry_root_cause_verified"])

    def test_success_exit_with_error_header_is_inconsistent(self):
        result = inspect(b"HTTP/2.0 409 Conflict\n", 0)
        self.assertEqual(result["classification"],
                         "EXIT_STATUS_AND_HTTP_STATUS_DISAGREE")
        self.assertFalse(result["contents_write_succeeded"])

    def test_error_exit_with_success_header_is_inconsistent(self):
        result = inspect(b"HTTP/2.0 201 Created\n", 1)
        self.assertEqual(result["classification"],
                         "EXIT_STATUS_AND_HTTP_STATUS_DISAGREE")
        self.assertFalse(result["contents_write_succeeded"])

    def test_redirect_is_not_success(self):
        result = inspect(b"HTTP/1.1 302 Found\n", 1)
        self.assertEqual(result["classification"], "UNEXPECTED_REDIRECT")
        self.assertFalse(result["contents_write_succeeded"])

    def test_multiline_response_is_not_accepted_as_first_line(self):
        result = inspect(b"HTTP/2.0 200 OK\nHTTP/2.0 409 Conflict\n", 1)
        self.assertIsNone(result["http_status"])

    def test_oversized_status_line_fails_closed(self):
        result = inspect(b"HTTP/2.0 201 " + b"x" * 5000 + b"\n", 0)
        self.assertIsNone(result["http_status"])
        self.assertFalse(result["contents_write_succeeded"])

    def test_redaction_keeps_token_and_body_out_of_result(self):
        secret = "ghp_PRIVATE_CANARY_DO_NOT_LOG"
        payload = ("HTTP/2.0 403 " + secret + "\r\n").encode()
        rendered = json.dumps(inspect(payload, 1))
        self.assertNotIn(secret, rendered)
        self.assertNotIn("PRIVATE_CANARY", rendered)
        self.assertIn("403", rendered)
        self.assertEqual(json.loads(rendered)["production_recommendations"],
                         "DISABLED")

    def test_malformed_arguments_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "INVALID_DIAGNOSTIC_ARGUMENTS"):
            inspect("HTTP/2.0 200 OK", 0)
        with self.assertRaisesRegex(ValueError, "INVALID_DIAGNOSTIC_ARGUMENTS"):
            inspect(b"HTTP/2.0 200 OK\n", "zero")


if __name__ == "__main__":
    unittest.main()
