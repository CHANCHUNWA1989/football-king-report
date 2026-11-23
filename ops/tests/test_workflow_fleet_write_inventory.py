"""Static fleet write inventory regression tests; no network or Git writes."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ops.workflow_fleet_write_inventory import WorkflowFleetHold, inventory


class WorkflowFleetWriteInventoryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]

    def test_actual_repo_fleet_finds_other_main_writers_not_just_iphone(self):
        result = inventory(self.root / ".github/workflows")
        # Bounded, secret-free evidence receipt in CI logs for reviewer audit.
        print("P0_569_FLEET_SUMMARY=" + json.dumps({
            "workflow_files_scanned": result["workflow_files_scanned"],
            "explicit_main_git_push_workflows": result["explicit_main_git_push_workflows"],
            "contents_api_mutation_workflows": result["contents_api_mutation_workflows"],
            "contents_write_permission_workflows": result["contents_write_permission_workflows"],
            "main_ruleset_activation_authorized": result["main_ruleset_activation_authorized"],
            "production_recommendations": result["production_recommendations"],
        }, sort_keys=True))
        self.assertGreaterEqual(result["workflow_files_scanned"], 60)
        self.assertIn("football-king-iphone.yml",
                      result["explicit_main_git_push_workflows"])
        self.assertIn("four-model-shadow-daily.yml",
                      result["explicit_main_git_push_workflows"])
        self.assertIn("football-king-odds.yml",
                      result["contents_api_mutation_workflows"])
        self.assertIn("private-all-market-research.yml",
                      result["contents_api_mutation_workflows"])
        self.assertIn("football-king-iphone.yml",
                      result["contents_write_permission_workflows"])
        self.assertFalse(result["repository_writer_inventory_exhaustive"])
        self.assertFalse(result["main_ruleset_activation_authorized"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_full_fleet_has_no_raw_source_lines_or_tokens_in_receipt(self):
        result = inventory(self.root / ".github/workflows")
        data = json.dumps(result, sort_keys=True)
        self.assertNotIn("GH_TOKEN:", data)
        self.assertNotIn("GITHUB_TOKEN:", data)
        self.assertNotIn("contents/$dest", data)
        self.assertNotIn("ssh-rsa", data)
        self.assertTrue(result["suspected_write_or_dynamic_action_indicators"])
        self.assertTrue(all(len(x["sha256"]) == 64
                            for x in result["suspected_write_or_dynamic_action_indicators"]))

    def test_all_workflows_get_scanned_not_only_iphone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.yml").write_text(
                "jobs:\n  x:\n    permissions:\n      contents: write\n"
                "    steps:\n      - run: git push origin HEAD:refs/heads/main\n")
            (root / "b.yaml").write_text(
                "jobs:\n  y:\n    steps:\n      - run: gh api -X PUT repos/org/repo/contents/test.json\n")
            (root / "c.yml").write_text("jobs:\n  z:\n    steps: []\n")
            receipt = inventory(root)
            self.assertEqual(receipt["workflow_files_scanned"], 3)
            self.assertEqual(receipt["explicit_main_git_push_workflows"], ["a.yml"])
            self.assertEqual(receipt["contents_api_mutation_workflows"], ["b.yaml"])
            self.assertEqual(receipt["contents_write_permission_workflows"], ["a.yml"])
            self.assertEqual(receipt["git_push_workflows"], ["a.yml"])
            self.assertFalse(receipt["main_ruleset_activation_authorized"])

    def test_comments_only_are_not_reported_as_actual_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "comment.yml").write_text(
                "jobs:\n  x:\n"
                "    # contents: write\n"
                "    # git push origin HEAD:refs/heads/main\n"
                "    # gh api -X PUT repos/x/contents/fake\n"
                "    steps:\n      - run: echo safe\n")
            receipt = inventory(root)
            self.assertEqual(receipt["explicit_main_git_push_workflows"], [])
            self.assertEqual(receipt["contents_api_mutation_workflows"], [])
            self.assertEqual(receipt["contents_write_permission_workflows"], [])
            self.assertEqual(receipt["status"], "HOLD_WORKFLOW_FLEET_CUTOVER_UNVERIFIED")

    def test_absence_of_detected_writes_never_authorizes_cutover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "safe.yml").write_text(
                "jobs:\n  x:\n    steps:\n      - run: echo synthetic\n")
            receipt = inventory(root)
            self.assertEqual(receipt["suspected_write_or_dynamic_action_indicators"], [])
            self.assertFalse(receipt["human_review_verified"])
            self.assertFalse(receipt["authenticated_remote_archive_canary_verified"])
            self.assertFalse(receipt["main_ruleset_activation_authorized"])
            self.assertEqual(receipt["production_recommendations"], "DISABLED")

    def test_missing_oversized_symlink_and_broken_directory_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            absent = root / "no-such-dir"
            with self.assertRaises(WorkflowFleetHold):
                inventory(absent)
            safe = root / "valid"
            safe.mkdir()
            with self.assertRaises(WorkflowFleetHold):
                inventory(safe)
            too_big = safe / "huge.yml"
            too_big.write_bytes(b"Z" * 1_000_001)
            with self.assertRaisesRegex(WorkflowFleetHold, "WORKFLOW_SIZE_LIMIT"):
                inventory(safe)
            too_big.unlink()
            (safe / "valid.yml").write_text("jobs:\n  x:\n    steps: []\n")
            link = safe / "link.yml"
            link.symlink_to(safe / "valid.yml")
            with self.assertRaisesRegex(WorkflowFleetHold,
                                        "UNSAFE_WORKFLOW_DIRECTORY_ENTRY"):
                inventory(safe)

    def test_deterministic_receipt_and_cli_always_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "fixture.yml").write_text(
                "jobs:\n  test:\n    steps:\n      - run: git push origin HEAD:refs/heads/main\n")
            first = inventory(root)
            second = inventory(root)
            self.assertEqual(first, second)
            proc = subprocess.run([
                sys.executable, "-m", "ops.workflow_fleet_write_inventory",
                "--workflows", str(root),
            ], capture_output=True, check=False, text=True, cwd=self.root)
            self.assertEqual(proc.returncode, 1)
            result = json.loads(proc.stdout)
            self.assertEqual(result["explicit_main_git_push_workflows"],
                             ["fixture.yml"])
            self.assertFalse(result["main_ruleset_activation_authorized"])


if __name__ == "__main__":
    unittest.main()
