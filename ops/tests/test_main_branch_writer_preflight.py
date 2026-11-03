"""Offline acceptance tests for conservative branch-write inventory."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from ops.main_branch_writer_preflight import _indicators, inventory, main


class MainWriterPreflightTests(unittest.TestCase):
    def make_root(self, tmp):
        root = Path(tmp)
        path = root / ".github" / "workflows"
        path.mkdir(parents=True)
        return root, path

    def test_detects_explicit_job_write_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, workflows = self.make_root(tmp)
            (workflows / "archive.yml").write_text(
                "name: Archive\njobs:\n  save:\n    permissions:\n"
                "      contents: write\n", encoding="utf-8")
            (workflows / "readonly.yaml").write_text(
                "permissions:\n  contents: read\n", encoding="utf-8")
            report = inventory(root)
            self.assertEqual(report["workflow_count"], 2)
            self.assertEqual(report["potential_repo_writer_count"], 1)
            self.assertEqual(report["potential_repo_writers"][0]["workflow"], "archive.yml")
            self.assertIn("contents_write_permission",
                          report["potential_repo_writers"][0]["indicators"])
            self.assertEqual(report["status"], "MIGRATION_REVIEW_REQUIRED")
            self.assertFalse(report["main_branch_protection_independently_verified"])
            self.assertFalse(report["all_indirect_writes_excluded"])
            self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_inline_write_all_git_push_and_gh_mutation_detected(self):
        self.assertIn("contents_write_permission",
                      _indicators("permissions: {contents: write}\n"))
        self.assertIn("write_all_permission",
                      _indicators("permissions: write-all\n"))
        self.assertIn("git_push",
                      _indicators("run: git push origin main\n"))
        self.assertIn("gh_api_mutation",
                      _indicators("run: gh api -X PUT repos/me/repo/contents/file\n"))

    def test_comment_only_permission_not_misclassified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, workflows = self.make_root(tmp)
            (workflows / "readonly.yml").write_text(
                "# contents: write\npermissions:\n  contents: read\n"
                "jobs:\n  test:\n    steps: []\n", encoding="utf-8")
            report = inventory(root)
            self.assertEqual(report["potential_repo_writer_count"], 0)
            self.assertEqual(report["status"], "NO_STATIC_CANDIDATES_BUT_UNVERIFIED")
            self.assertFalse(report["main_branch_protection_independently_verified"])

    def test_missing_or_empty_workflows_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "missing or symlinked"):
                inventory(root)
            self.make_root(tmp)
            with self.assertRaisesRegex(ValueError, "no workflow files"):
                inventory(root)

    def test_cli_strict_mode_blocks_candidate_without_mutating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, workflows = self.make_root(tmp)
            path = workflows / "writer.yml"
            original = "permissions:\n  contents: write\n"
            path.write_text(original, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(["--root", str(root),
                                  "--require-no-writer-candidates"])
            self.assertEqual(exit_code, 2)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "MIGRATION_REVIEW_REQUIRED")
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_cli_read_only_does_not_claim_release_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, workflows = self.make_root(tmp)
            (workflows / "reader.yml").write_text(
                "permissions:\n  contents: read\n", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = main(["--root", str(root),
                                  "--require-no-writer-candidates"])
            self.assertEqual(exit_code, 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "NO_STATIC_CANDIDATES_BUT_UNVERIFIED")
            self.assertFalse(result["external_reviewer_approved"])

    def test_symlinked_workflow_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, workflows = self.make_root(tmp)
            target = Path(tmp) / "real.yml"
            target.write_text("permissions:\n  contents: read\n", encoding="utf-8")
            (workflows / "linked.yml").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "not a regular file"):
                inventory(root)


if __name__ == "__main__":
    unittest.main()
