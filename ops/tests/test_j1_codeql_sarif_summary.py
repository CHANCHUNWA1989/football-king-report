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
