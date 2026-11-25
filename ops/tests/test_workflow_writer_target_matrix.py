"""Pinned default-main writer targets drift check for 15 reviewed workflows.

This asserts literal code-path evidence only. Passing never grants main Ruleset,
archive migration, source trust, real betting or production authorization.
"""

from pathlib import Path
import re
import unittest


# Markers were verified against main at
# 3ce493fbeb9bfea29af1b93064a085afe8efb280 (2026-11-23 HKT).
# A renamed job/target should trigger an independent reviewer re-audit.
TARGETS = {
    "football-king-asia-apis.yml":
        ("archive", ("sources/asia_api_latest.json",)),
    "football-king-bsd-free.yml":
        ("archive", ("sources/bsd_history/", "sources/bsd_status_latest.json",
                     "sources/bsd_market_latest.json")),
    "football-king-german-live.yml":
        ("archive", ("sources/live_germany/history/", "sources/live_germany_latest.json")),
    "football-king-hkjc-free-research.yml":
        ("archive", ("sources/hkjc_tipsme_free_latest.json",)),
    "football-king-iphone.yml":
        ("archive", ("ops/archive_prepare.py", "ops/archive_forecast_provenance.py",
                     "contents/evidence/settled.json")),
    "football-king-japan-free-market.yml":
        ("archive", ("market/japan_free_status.json",)),
    "football-king-odds.yml":
        ("archive", ("market/history/", "market/collection_status.json",
                     "market/latest.json")),
    "football-king-research-extensions.yml":
        ("archive", ("sources/research_extensions_history/",
                     "sources/research_extensions_latest.json")),
    "football-king-secondary-sources.yml":
        ("archive", ("sources/history/", "sources/latest.json")),
    "football-king-six-free-upgrade.yml":
        ("archive", ("sources/six_league_quality_history/",
                     "sources/six_league_free_latest.json",
                     "sources/seven_quality_gates_latest.json",
                     "sources/six_league_fixture_overlap_latest.json")),
    "football-king-weather.yml":
        ("archive", ("sources/weather_history/", "sources/weather_latest.json")),
    "football-king-weekly.yml":
        ("weekly-report", ("reports/weekly/",)),
    "football-king-wide-free.yml":
        ("archive", ("sources/wide/history/", "sources/wide_latest.json")),
    "private-all-market-research.yml":
        ("archive_redacted_coverage", ("market/private_summary_latest.json",)),
    "four-model-shadow-daily.yml":
        ("archive_ndr_capture", ("ops.archive_ndr_capture_provenance",
                                 "ops.archive_openliga_capture")),
}
DIRECT_MAIN = {"football-king-iphone.yml", "four-model-shadow-daily.yml"}


class WorkflowWriterTargetMatrixTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.workflows = self.root / ".github" / "workflows"

    def test_all_15_reviewed_writers_still_match_visible_code_targets(self):
        self.assertEqual(len(TARGETS), 15)
        for filename, (job, markers) in TARGETS.items():
            with self.subTest(workflow=filename):
                source = (self.workflows / filename).read_text(encoding="utf-8")
                self.assertIn("  " + job + ":", source)
                self.assertIn("contents: write", source)
                for marker in markers:
                    self.assertIn(marker, source)
                if filename in DIRECT_MAIN:
                    self.assertIn("push origin HEAD:refs/heads/main", source)
                else:
                    self.assertIn("gh api -X PUT", source)
                    self.assertIn("contents/", source)
                self.assertNotIn("-f branch=", source)
                self.assertNotIn("-F branch=", source)

    def test_four_direct_main_job_blocks_are_not_forgotten(self):
        for filename, job_names in (
            ("football-king-iphone.yml", ("archive_provenance", "archive")),
            ("four-model-shadow-daily.yml",
             ("archive_ndr_capture", "archive_openliga_capture")),
        ):
            with self.subTest(workflow=filename):
                source = (self.workflows / filename).read_text(encoding="utf-8")
                for name in job_names:
                    self.assertRegex(source, re.compile(
                        r"(?m)^  " + re.escape(name) + r":\s*$"))
                self.assertGreaterEqual(
                    source.count("push origin HEAD:refs/heads/main"), 2)
                self.assertIn("contents: write", source)

    def test_iphone_legacy_two_source_split_and_consumers_still_visible(self):
        source = (self.workflows / "football-king-iphone.yml").read_text(
            encoding="utf-8")
        for marker in (
            "--previous evidence/settled.json",
            "--settled evidence/settled.json",
            '--input "$RUNNER_TEMP/settled.json"',
            "sources/latest.json", "sources/bsd_status_latest.json",
            "sources/bsd_market_latest.json", "sources/weather_latest.json",
            "sources/wide_latest.json", "sources/research_extensions_latest.json",
            "market/private_summary_latest.json", "market/japan_free_status.json",
            "market/latest.json", "sources/seven_quality_gates_latest.json",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

    def test_archive_proof_direct_main_helper_path_families(self):
        checks = {
            "ops/archive_prepare.py": (
                '"history"', '"shadow"', '"research_pairs"',
                '"worldwide_shadow"', '"verification_slates"'),
            "ops/archive_ndr_capture_provenance.py": (
                '"ndr_capture_provenance"',),
            "ops/archive_openliga_capture.py": (
                '"openliga_capture_provenance"',),
        }
        for filename, markers in checks.items():
            with self.subTest(helper=filename):
                source = (self.root / filename).read_text(encoding="utf-8")
                for marker in markers:
                    self.assertIn(marker, source)

    def test_reviewed_target_matrix_document_is_complete_and_stays_hold(self):
        content = (self.root /
                   "docs/P0_569_15_WORKFLOW_WRITE_TARGET_MATRIX_2026_11_23.md"
                   ).read_text(encoding="utf-8")
        self.assertIn("3ce493fbeb9bfea29af1b93064a085afe8efb280", content)
        for filename in TARGETS:
            with self.subTest(workflow=filename):
                self.assertIn(filename, content)
        self.assertIn("Ruleset activation authorized: false", content)
        self.assertIn("Production recommendations: DISABLED", content)


if __name__ == "__main__":
    unittest.main()
