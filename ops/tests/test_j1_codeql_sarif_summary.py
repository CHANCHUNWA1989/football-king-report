"""Synthetic SARIF-only coverage for the J1 CodeQL evidence handoff."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from j1_codeql_sarif_summary import _markdown, _tier, main, summarize_sarif


def sarif(results, rules=None):
    return {
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "CodeQL", "rules": rules or []}},
            "results": results,
        }],
    }


def finding(rule="py/example", uri="ops/japan_free_market.py", score=None):
    result = {
        "ruleId": rule,
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}}}],
        "message": {"text": "DONOTPRINT_PRIVATE_KEY_OR_SOURCE_QUOTE"},
    }
    if score is not None:
        result["properties"] = {"security-severity": str(score)}
    return result


class J1CodeQLSarifSummaryTests(unittest.TestCase):
    def test_valid_empty_sarif_is_observed_zero_not_review_approval(self):
        summary = summarize_sarif(sarif([]))
        self.assertEqual(summary["all_finding_count"], 0)
        self.assertEqual(summary["j1_parser_high_critical_gate"], "PASS")
        self.assertTrue(summary["human_review_required"])
        self.assertFalse(summary["source_quote_or_model_authentication"])

    def test_security_severity_rule_metadata_and_specific_j1_path(self):
        data = sarif([
            finding("py/real-rule"),
            finding("py/medium", "ops/other_module.py", 5.2),
        ], [{"id": "py/real-rule", "properties": {"security-severity": "7.8"}}])
        result = summarize_sarif(data)
        self.assertEqual(result["all_finding_count"], 2)
        self.assertEqual(result["all_by_severity"]["high"], 1)
        self.assertEqual(result["j1_parser_by_severity"]["high"], 1)
        self.assertEqual(result["j1_parser_high_critical_gate"], "FAIL")
        self.assertEqual(result["j1_rule_ids_top10"][0]["rule_id"], "py/real-rule")

    def test_absolute_codeql_uri_still_recognizes_the_j1_parser(self):
        data = sarif([finding(uri="file:///home/runner/work/repo/repo/ops/japan_free_market.py", score=9.8)])
        result = summarize_sarif(data)
        self.assertEqual(result["j1_parser_finding_count"], 1)
        self.assertEqual(result["j1_parser_by_severity"]["critical"], 1)

    def test_other_files_high_do_not_claim_j1_parser_failure(self):
        data = sarif([finding(uri="ops/unrelated.py", score=8.0)])
        result = summarize_sarif(data)
        self.assertEqual(result["all_by_severity"]["high"], 1)
        self.assertEqual(result["j1_parser_finding_count"], 0)
        self.assertEqual(result["j1_parser_high_critical_gate"], "PASS")
        self.assertTrue(result["human_review_required"])

    def test_unrated_finding_stays_unrated_not_zero(self):
        result = summarize_sarif(sarif([finding()]))
        self.assertEqual(result["all_finding_count"], 1)
        self.assertEqual(result["j1_parser_by_severity"]["unrated"], 1)
        self.assertTrue(result["human_review_required"])

    def test_bad_sarif_fails_closed(self):
        for item in ({}, {"version": "2.1.0"}, {"version": "2.0.0", "runs": []},
                     {"version": "2.1.0", "runs": [{"tool": {"driver": {}}}]}):
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    summarize_sarif(item)

    def test_non_finite_or_malformed_severity_cannot_pass_as_high(self):
        for v in ("NaN", "Infinity", "unexpected", -3, 11, None):
            with self.subTest(v=v):
                self.assertEqual(_tier(v), "unrated")

    def test_untrusted_rule_id_is_sanitized_and_private_message_not_logged(self):
        result = summarize_sarif(sarif([finding("secret\ncanary")]))
        self.assertEqual(result["j1_rule_ids_top10"][0]["rule_id"], "unidentified-rule")
        rendered = json.dumps(result) + _markdown(result)
        self.assertNotIn("DONOTPRINT_PRIVATE_KEY_OR_SOURCE_QUOTE", rendered)
        self.assertNotIn("secret\ncanary", rendered)
        self.assertIn("human review", rendered.lower())

    def test_diagnostic_and_metric_rules_are_not_called_security_findings(self):
        data = sarif([
            finding("py/diagnostics/successfully-extracted-files", "ops/x.py"),
            finding("py/diagnostics/extraction-warnings", "ops/x.py"),
            finding("py/summary/lines-of-code", "ops/x.py"),
            finding("py/unscored-other", "ops/x.py"),
            finding("py/scored-security", "ops/japan_free_market.py", 8.5),
        ])
        result = summarize_sarif(data)
        self.assertEqual(result["all_finding_count"], 5)
        self.assertEqual(result["all_by_category"], {
            "diagnostic": 2, "metric": 1, "severity_scored": 1,
            "other_unrated": 1,
        })
        self.assertEqual(result["j1_parser_by_category"]["severity_scored"], 1)
        self.assertEqual(result["j1_parser_high_critical_gate"], "FAIL")

    def test_same_unrated_status_does_not_prove_diagnostic(self):
        data = sarif([
            finding("py/diagnostics/extraction-warnings"),
            finding("py/unknown-unscored"),
        ])
        result = summarize_sarif(data)
        self.assertEqual(result["all_by_severity"]["unrated"], 2)
        self.assertEqual(result["all_by_category"]["diagnostic"], 1)
        self.assertEqual(result["all_by_category"]["other_unrated"], 1)
        self.assertTrue(result["human_review_required"])

    def test_all_repository_rule_ids_are_sanitized_counted_and_stably_sorted(self):
        data = sarif([
            finding("py/diagnostics/warnings", uri="ops/f.py"),
            finding("py/diagnostics/warnings", uri="ops/g.py"),
            finding("py/summary/lines-of-code", uri="ops/h.py"),
            finding("private-path\\nSECRET", uri="ops/i.py"),
        ])
        result = summarize_sarif(data)
        self.assertEqual(result["all_rule_ids_top20"], [
            {"rule_id": "py/diagnostics/warnings", "count": 2, "category": "diagnostic"},
            {"rule_id": "py/summary/lines-of-code", "count": 1, "category": "metric"},
            {"rule_id": "unidentified-rule", "count": 1, "category": "other_unrated"},
        ])
        rendered = _markdown(result) + json.dumps(result)
        self.assertNotIn("SECRET", rendered)
        self.assertNotIn("DONOTPRINT_PRIVATE_KEY_OR_SOURCE_QUOTE", rendered)
        self.assertNotIn("ops/g.py", rendered)

    def test_unrated_high_severity_from_broken_score_stays_under_review(self):
        data = sarif([finding("py/code-injection", score="not-a-number")])
        result = summarize_sarif(data)
        self.assertEqual(result["all_by_category"]["other_unrated"], 1)
        self.assertEqual(result["j1_parser_high_critical_gate"], "PASS")
        self.assertTrue(result["human_review_required"])

    def test_no_security_severity_claim_when_only_diagnostics_are_in_sarif(self):
        data = sarif([
            finding("py/diagnostics/successfully-extracted-files", "ops/other.py"),
            finding("py/summary/lines-of-user-code", "ops/other.py"),
        ])
        result = summarize_sarif(data)
        self.assertEqual(result["all_by_category"]["diagnostic"], 1)
        self.assertEqual(result["all_by_category"]["metric"], 1)
        self.assertEqual(result["all_by_category"]["severity_scored"], 0)
        self.assertEqual(result["all_by_category"]["other_unrated"], 0)
        self.assertFalse(result["source_quote_or_model_authentication"])

    def test_unscored_non_diagnostic_in_j1_parser_requires_security_review(self):
        # A CodeQL rule without a numeric security-severity is not harmless.
        # The market parser must fail closed pending human triage.
        result = summarize_sarif(sarif([
            finding("py/incomplete-url-substring-sanitization", score=None),
        ]))
        self.assertEqual(result["j1_parser_by_category"]["other_unrated"], 1)
        self.assertEqual(result["j1_parser_security_review_gate"], "FAIL")

    def test_j1_diagnostic_only_does_not_fail_security_review_gate(self):
        result = summarize_sarif(sarif([
            finding("py/diagnostics/extraction-warnings", score=None),
        ]))
        self.assertEqual(result["j1_parser_by_category"]["diagnostic"], 1)
        self.assertEqual(result["j1_parser_security_review_gate"], "PASS")

    def test_cli_returns_nonzero_for_j1_unscored_non_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "python.sarif").write_text(
                json.dumps(sarif([
                    finding("py/incomplete-url-substring-sanitization"),
                ])), encoding="utf-8"
            )
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}):
                with patch("builtins.print") as output:
                    code = main(["--directory", directory])
            self.assertEqual(code, 2)
            self.assertIn('"j1_parser_security_review_gate":"FAIL"', output.call_args.args[0])
            self.assertNotIn("DONOTPRINT_PRIVATE_KEY_OR_SOURCE_QUOTE", output.call_args.args[0])

    def test_public_tracked_python_path_only_includes_known_repository_files(self):
        data = sarif([
            finding("py/incomplete-url-substring-sanitization", "ops/trusted_reader.py"),
            finding("py/incomplete-url-substring-sanitization", "ops/trusted_reader.py"),
            finding("py/unrated", "ops/unknown_vendor.py"),
        ])
        output = summarize_sarif(
            data, tracked_public_paths={"ops/trusted_reader.py"}
        )
        self.assertEqual(output["public_tracked_python_paths_top20"], [
            {"path": "ops/trusted_reader.py", "count": 2},
        ])
        self.assertEqual(output["unmapped_public_location_count"], 1)
        self.assertNotIn("DONOTPRINT_PRIVATE_KEY_OR_SOURCE_QUOTE", json.dumps(output))

    def test_public_paths_accept_absolute_runner_uri_if_tracked(self):
        item = finding(
            "py/incomplete-url-substring-sanitization",
            "file:///home/runner/work/project/project/ops/trusted_reader.py",
        )
        data = sarif([item])
        output = summarize_sarif(
            data, tracked_public_paths={"ops/trusted_reader.py"}
        )
        self.assertEqual(output["public_tracked_python_paths_top20"][0]["path"],
                         "ops/trusted_reader.py")

    def test_public_paths_reject_traversal_urls_and_untracked_paths(self):
        urls = [
            "file:///runner/work/repo/repo/ops/../ops/trusted_reader.py",
            "https://private.example/secrets/ops/trusted_reader.py",
            "../../ops/trusted_reader.py",
            "ops/private_nonrepo.py",
        ]
        output = summarize_sarif(
            sarif([finding(uri=value) for value in urls]),
            tracked_public_paths={"ops/trusted_reader.py"}
        )
        self.assertEqual(output["public_tracked_python_paths_top20"], [])
        self.assertEqual(output["unmapped_public_location_count"], 4)
        self.assertNotIn("private.example", json.dumps(output))

    def test_public_path_report_opt_in_and_sanitized_markdown(self):
        data = sarif([finding(
            "py/incomplete-url-substring-sanitization", "ops/trusted_reader.py"
        )])
        ordinary = summarize_sarif(data)
        self.assertNotIn("public_tracked_python_paths_top20", ordinary)
        output = summarize_sarif(
            data, tracked_public_paths={"ops/trusted_reader.py"}
        )
        rendered = _markdown(output) + json.dumps(output)
        self.assertIn("ops/trusted_reader.py", rendered)
        self.assertNotIn("DONOTPRINT_PRIVATE_KEY_OR_SOURCE_QUOTE", rendered)

    def test_cli_no_local_sarif_returns_nonzero_without_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("builtins.print") as output:
                result = main(["--directory", directory])
            self.assertEqual(result, 3)
            self.assertIn("J1_CODEQL_SUMMARY_ERROR=", output.call_args.args[0])
            self.assertNotIn(directory, output.call_args.args[0])

    def test_cli_reads_sarif_and_appends_summary_without_original_message(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "python.sarif").write_text(
                json.dumps(sarif([finding(score=4.8)])), encoding="utf-8"
            )
            summary_file = Path(directory, "summary.md")
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_file)}):
                with patch("builtins.print") as output:
                    result = main(["--directory", directory])
            self.assertEqual(result, 0)
            self.assertIn("J1_CODEQL_SUMMARY=", output.call_args.args[0])
            self.assertNotIn("DONOTPRINT_PRIVATE_KEY_OR_SOURCE_QUOTE", output.call_args.args[0])
            md = summary_file.read_text(encoding="utf-8")
            self.assertIn("medium", md)
            self.assertNotIn("DONOTPRINT_PRIVATE_KEY_OR_SOURCE_QUOTE", md)

    def test_cli_fails_on_j1_high_severity_even_when_scan_parse_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "python.sarif").write_text(
                json.dumps(sarif([finding(score=7.0)])), encoding="utf-8"
            )
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}):
                with patch("builtins.print") as output:
                    result = main(["--directory", directory])
            self.assertEqual(result, 2)
            self.assertIn('"j1_parser_high_critical_gate":"FAIL"', output.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
