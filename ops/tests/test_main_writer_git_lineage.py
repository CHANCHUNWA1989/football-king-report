"""S0 read-only Git lineage assertions use local Git only; no remote provider."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ops.main_writer_git_lineage import capture, classify, main


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def add(root, name, content="synthetic research only"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(root, "add", "--", name)
    git(root, "commit", "-qm", f"Synthetic local fixture {name}")
    return git(root, "rev-parse", "HEAD")


def repo(root):
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Offline git fixture")
    add(root, "README.md")
    return root


class MainGitLineageTests(unittest.TestCase):
    def test_observes_actual_changed_paths_and_exact_main_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(Path(tmp) / "main")
            a = add(root, "sources/bsd_status_latest.json", "{}")
            b = add(root, "market/latest.json", "{}")
            c = add(root, "evidence/settled.json", "[]")
            report = capture(root, now=datetime(2026, 11, 3, tzinfo=timezone.utc))
            self.assertEqual(report["status"],
                             "PARTIAL_REAL_MAIN_GIT_COMMIT_LINEAGE_CAPTURED")
            self.assertEqual(report["main_head_sha"], c)
            self.assertEqual(report["sampled_commit_count"], 4)
            self.assertEqual(report["matching_commit_count"], 3)
            self.assertTrue(report["sampled_history_complete"])
            self.assertFalse(report["shallow_checkout"])
            self.assertEqual(report["main_write_path_categories"], {
                "BSD_STATUS_MAIN_WRITE": 1,
                "LEGACY_SETTLEMENT_MAIN_WRITE": 1,
                "MARKET_RESEARCH_MAIN_WRITE": 1,
            })
            by_sha = {x["commit_sha"]: x["candidate_write_paths"]
                      for x in report["commit_path_evidence"]}
            self.assertEqual(by_sha[a][0]["path"],
                             "sources/bsd_status_latest.json")
            self.assertEqual(by_sha[b][0]["category"],
                             "MARKET_RESEARCH_MAIN_WRITE")
            self.assertIn(c, by_sha)
            self.assertFalse(report["writer_workflow_attribution_independently_verified"])
            self.assertFalse(report["all_dynamic_writers_and_readers_audited"])
            self.assertFalse(report["permission_to_merge"])
            self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_code_only_change_does_not_invent_writer_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(Path(tmp) / "main")
            add(root, "ops/new_reader.py", "print('read only')")
            result = capture(root)
            self.assertEqual(result["matching_commit_count"], 0)
            self.assertEqual(result["sampled_path_change_count"], 2)
            self.assertFalse(result["all_dynamic_writers_and_readers_audited"])
            self.assertFalse(result["full_s0_acceptance"])

    def test_known_history_and_provenance_paths_are_categorized(self):
        self.assertEqual(classify("history/2026/11/03/run.json.gz"),
                         "RESEARCH_HISTORY_MAIN_WRITE")
        self.assertEqual(classify("forecast_provenance/2026/11/03/data.json"),
                         "FORECAST_PROVENANCE_MAIN_WRITE")
        self.assertEqual(classify("sources/another_latest.json"),
                         "OTHER_SOURCE_MAIN_WRITE")
        self.assertIsNone(classify("ops/source_reader.py"))

    def test_not_main_checkout_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(Path(tmp) / "repo")
            git(root, "checkout", "-qb", "research")
            with self.assertRaisesRegex(ValueError, "NOT_CHECKED_OUT_MAIN_BRANCH"):
                capture(root)

    def test_non_repo_and_symlink_checkout_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ordinary = base / "ordinary"
            ordinary.mkdir()
            with self.assertRaisesRegex(ValueError, "MAIN_GIT_QUERY_FAILED"):
                capture(ordinary)
            root = repo(base / "repo")
            link = base / "mainlink"
            link.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "MAIN_CHECKOUT_NOT_DIRECTORY"):
                capture(link)

    def test_bound_sampling_does_not_claim_complete_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(Path(tmp) / "repo")
            add(root, "sources/latest.json", "{}")
            add(root, "market/latest.json", "{}")
            r = capture(root, max_commits=2)
            self.assertEqual(r["sampled_commit_count"], 2)
            self.assertFalse(r["sampled_history_complete"])
            self.assertEqual(r["matching_commit_count"], 2)
            for n in (0, 121, -1, True, "10"):
                with self.subTest(limit=n):
                    with self.assertRaisesRegex(ValueError, "INVALID_MAIN_HISTORY_LIMIT"):
                        capture(root, max_commits=n)

    def test_shallow_checkout_always_reports_incomplete_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = repo(base / "repo")
            add(root, "sources/bsd_status_latest.json", "{}")
            clone = base / "shallow"
            subprocess.run(["git", "clone", "-q", "--depth=1",
                            "--branch", "main", root.as_uri(), str(clone)],
                           check=True, capture_output=True, text=True)
            r = capture(clone)
            self.assertTrue(r["shallow_checkout"])
            self.assertFalse(r["sampled_history_complete"])
            self.assertEqual(r["matching_commit_count"], 1)

    def test_cli_output_exclusive_and_does_not_change_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = repo(base / "repo")
            head = add(root, "evidence/settled.json", "[]")
            output = base / "receipt.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = main(["--main-checkout", str(root), "--output", str(output)])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(output.read_text())["main_head_sha"], head)
            previous = output.read_bytes()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    main(["--main-checkout", str(root), "--output", str(output)]), 2)
            self.assertEqual(previous, output.read_bytes())
            self.assertEqual(git(root, "rev-parse", "HEAD"), head)
            self.assertIn("MAIN_RUNTIME_LINEAGE_AUDIT_INCOMPLETE",
                          stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
