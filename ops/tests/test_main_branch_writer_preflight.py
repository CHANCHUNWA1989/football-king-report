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


    def test_maps_literal_shared_path_without_claiming_verified_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, workflows = self.make_root(tmp)
            (workflows / "writer.yml").write_text(
                "permissions:\n  contents: write\n"
                "jobs:\n  archive:\n    steps:\n"
                "    - run: gh api -X PUT repos/repo/contents/sources/latest.json\n",
                encoding="utf-8")
            (workflows / "reader.yml").write_text(
                "permissions:\n  contents: read\n"
                "jobs:\n  reader:\n    steps:\n"
                "    - run: python ops/source_overlay.py --input sources/latest.json\n",
                encoding="utf-8")
            (root / "ops").mkdir()
            (root / "ops" / "source_overlay.py").write_text(
                'SOURCE="sources/latest.json"\n', encoding="utf-8")
            result = inventory(root)
            self.assertEqual(result["workflow_count"], 2)
            self.assertEqual(result["potential_repo_writer_count"], 1)
            self.assertEqual(result["candidate_cross_workflow_path_overlap_count"], 1)
            self.assertEqual(
                result["candidate_cross_workflow_path_overlaps"][0][
                    "shared_path_mentions_not_verified_direction"],
                ["sources/latest.json"])
            self.assertEqual(result["direct_ops_scripts_scanned"], 1)
            self.assertEqual(result["direct_ops_script_mutation_candidate_count"], 0)
            self.assertFalse(result["consumer_directions_and_write_targets_verified"])
            self.assertFalse(result["main_branch_protection_independently_verified"])
            self.assertFalse(result["external_reviewer_approved"])

    def test_referenced_script_mutation_candidate_stays_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, workflows = self.make_root(tmp)
            (workflows / "task.yml").write_text(
                "permissions:\n  contents: read\n"
                "jobs:\n  task:\n    steps:\n"
                "    - run: python ops/archiver.py\n",
                encoding="utf-8")
            (root / "ops").mkdir()
            (root / "ops" / "archiver.py").write_text(
                'subprocess.run(["git", "push", "origin", "main"])\n'
                'cmd = "git push origin main"\n', encoding="utf-8")
            result = inventory(root)
            self.assertEqual(result["direct_ops_script_mutation_candidate_count"], 1)
            self.assertIn("git_push",
                          result["direct_ops_script_mutation_candidates"][0][
                              "mutation_markers"])
            self.assertEqual(result["status"], "NO_STATIC_CANDIDATES_BUT_UNVERIFIED")
            self.assertFalse(result["all_indirect_writes_excluded"])

    def test_missing_direct_script_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, workflows = self.make_root(tmp)
            (workflows / "call.yml").write_text(
                "jobs:\n  x:\n    steps:\n    - run: python ops/missing.py\n",
                encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "referenced ops script missing"):
                inventory(root)

    def test_exclusive_output_refuses_overwriting_prior_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, workflows = self.make_root(tmp)
            (workflows / "read.yml").write_text(
                "permissions:\n  contents: read\n", encoding="utf-8")
            output_path = root / "inventory.json"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["--root", str(root),
                                       "--output", str(output_path)]), 0)
            original = output_path.read_bytes()
            self.assertEqual(json.loads(original)["workflow_count"], 1)
            output2 = io.StringIO()
            with contextlib.redirect_stdout(output2):
                self.assertEqual(main(["--root", str(root),
                                       "--output", str(output_path)]), 2)
            self.assertEqual(original, output_path.read_bytes())
            self.assertEqual(json.loads(output2.getvalue())["status"],
                             "AUDIT_FAILED")

    def test_writer_workflow_symlink_refused_before_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, workflows = self.make_root(tmp)
            target = root / "outside.yml"
            target.write_text("permissions:\n  contents: write\n", encoding="utf-8")
            (workflows / "writer.yml").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "not a regular file"):
                inventory(root)


if __name__ == "__main__":
    unittest.main()
