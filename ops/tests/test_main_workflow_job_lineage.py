"""Read-only tests for one pinned historical GitHub run/job→main path mapping."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ops.main_workflow_job_lineage as m


def run_fixture():
    return {
        "id": m.RUN_ID, "name": m.WORKFLOW_NAME,
        "head_branch": "main", "head_sha": m.RUN_HEAD,
        "run_attempt": 1, "status": "completed", "conclusion": "success",
        "event": "schedule", "repository": {"full_name": m.REPOSITORY},
    }


def jobs_fixture():
    rows = [
        {"name": name, "id": ident, "run_id": m.RUN_ID,
         "status": "completed", "conclusion": "success"}
        for name, ident in m.JOBS.items()
    ]
    rows.append({"name": "publish", "id": 123, "run_id": m.RUN_ID,
                 "status": "completed", "conclusion": "success"})
    return {"total_count": len(rows), "jobs": rows}


def job_log(name):
    commit, paths = (
        (m.ARCHIVE_SHA, m.ARCHIVE_PATHS) if name == "archive" else
        (m.PROVENANCE_SHA, m.PROVENANCE_PATHS)
    )
    return (
        f"2026-11-03T08:26:40Z [detached HEAD {commit[:7]}] "
        f"Archive research snapshots for run {m.RUN_ID}\n"
        + "\n".join(" create mode 100644 " + path for path in paths) +
        "\nTo https://github.com/" + m.REPOSITORY + "\n"
        "  old..new  HEAD -> main\n"
    )


def fake_git(root, *args):
    if args == ("symbolic-ref", "--quiet", "--short", "HEAD"):
        return "main"
    if args == ("rev-parse", "--verify", "HEAD"):
        return m.PROVENANCE_SHA
    if args == ("rev-parse", f"{m.ARCHIVE_SHA}^"):
        return m.RUN_HEAD
    if args == ("rev-parse", f"{m.PROVENANCE_SHA}^"):
        return m.ARCHIVE_SHA
    if args[-1] == m.ARCHIVE_SHA and args[0] == "diff-tree":
        return "\n".join(m.ARCHIVE_PATHS)
    if args[-1] == m.PROVENANCE_SHA and args[0] == "diff-tree":
        return "\n".join(m.PROVENANCE_PATHS)
    raise AssertionError(f"unexpected read-only Git query: {args}")


class MainWorkflowJobLineageTests(unittest.TestCase):
    def test_pinned_runtime_correlates_two_jobs_without_overclaiming(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(m, "_git", side_effect=fake_git), patch.object(
                    m.subprocess, "run", return_value=SimpleNamespace(returncode=0)):
                r = m.corroborate(Path(tmp), run_fixture(), jobs_fixture(),
                                  job_log("archive"), job_log("archive_provenance"))
            self.assertEqual(r["status"],
                             "TWO_HISTORICAL_MAIN_WRITER_JOBS_CORROBORATED")
            self.assertEqual(r["run_id"], m.RUN_ID)
            self.assertEqual([x["commit_sha"] for x in
                              r["historical_commit_job_pairs"]],
                             [m.ARCHIVE_SHA, m.PROVENANCE_SHA])
            self.assertTrue(all(x["main_push_logged"] for x in
                                r["historical_commit_job_pairs"]))
            for flag in ("all_main_writers_identified",
                         "all_dynamic_reader_edges_checked",
                         "github_branch_protection_enforced",
                         "independent_reviewer_approved",
                         "independent_external_timing_verified",
                         "real_bsd_archive_cutover_completed",
                         "permission_to_merge_or_deploy", "verified_positive_ev"):
                self.assertFalse(r[flag], flag)
            self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_run_identity_attempt_branch_and_success_required(self):
        for field, bad in [
            ("id", m.RUN_ID+1), ("name", "Other Workflow"),
            ("head_branch", "audit"), ("head_sha", "f"*40),
            ("run_attempt", 2), ("status", "queued"),
            ("conclusion", "failure"), ("event", "push"),
        ]:
            with self.subTest(field=field):
                r = run_fixture()
                r[field] = bad
                with self.assertRaisesRegex(ValueError, "S0_WRONG_WORKFLOW_RUN"):
                    m._run_metadata(r, jobs_fixture())
        r = run_fixture()
        r["repository"] = {"full_name": "attacker/other-repo"}
        with self.assertRaisesRegex(ValueError, "S0_RUN_REPOSITORY_MISMATCH"):
            m._run_metadata(r, jobs_fixture())

    def test_incomplete_jobs_or_wrong_role_rejected(self):
        j = jobs_fixture()
        j["total_count"] = 9
        with self.assertRaisesRegex(ValueError, "S0_INCOMPLETE_JOBS_RESPONSE"):
            m._run_metadata(run_fixture(), j)
        j = jobs_fixture()
        j["jobs"][0]["id"] = 3
        with self.assertRaisesRegex(ValueError, "S0_JOB_ID_OR_RESULT_MISMATCH"):
            m._run_metadata(run_fixture(), j)
        j = jobs_fixture()
        j["jobs"] = [x for x in j["jobs"] if x["name"] != "archive"]
        j["total_count"] = len(j["jobs"])
        with self.assertRaisesRegex(ValueError, "S0_REQUIRED_ARCHIVE_JOBS_MISSING"):
            m._run_metadata(run_fixture(), j)

    def test_job_log_requires_branch_push_sha_run_and_all_paths(self):
        original = job_log("archive")
        for bad in [
            original.replace("HEAD -> main", "HEAD -> archive"),
            original.replace(m.ARCHIVE_SHA[:7], "0000000"),
            original.replace(str(m.RUN_ID), "00000000"),
            original.replace(m.ARCHIVE_PATHS[0], "other/unrelated.json"),
        ]:
            with self.subTest(log=bad[:90]):
                with self.assertRaisesRegex(
                        ValueError, "S0_JOB_LOG_COMMIT_PATH_OR_PUSH_UNVERIFIED"):
                    m._confirm_log(bad, sha=m.ARCHIVE_SHA, job="archive",
                                   paths=m.ARCHIVE_PATHS)

    def test_unexpected_git_paths_rejected_even_when_job_logs_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            def altered_git(root, *args):
                if args[0] == "diff-tree" and args[-1] == m.ARCHIVE_SHA:
                    return "sources/not-verified.json\n"
                return fake_git(root, *args)
            with patch.object(m, "_git", side_effect=altered_git), patch.object(
                    m.subprocess, "run", return_value=SimpleNamespace(returncode=0)):
                with self.assertRaisesRegex(
                        ValueError, "S0_ARCHIVE_COMMIT_CHANGED_FILES_MISMATCH"):
                    m.corroborate(Path(tmp), run_fixture(), jobs_fixture(),
                                  job_log("archive"), job_log("archive_provenance"))

    def test_not_main_branch_or_parent_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            def wrong_branch(root, *args):
                if args[0] == "symbolic-ref":
                    return "release"
                return fake_git(root, *args)
            with patch.object(m, "_git", side_effect=wrong_branch):
                with self.assertRaisesRegex(ValueError, "S0_NOT_ON_MAIN_BRANCH"):
                    m.corroborate(Path(tmp), run_fixture(), jobs_fixture(),
                                  job_log("archive"), job_log("archive_provenance"))
            def wrong_parent(root, *args):
                if args == ("rev-parse", f"{m.ARCHIVE_SHA}^"):
                    return "0"*40
                return fake_git(root, *args)
            with patch.object(m, "_git", side_effect=wrong_parent):
                with self.assertRaisesRegex(
                        ValueError, "S0_ARCHIVE_COMMIT_PARENT_MISMATCH"):
                    m.corroborate(Path(tmp), run_fixture(), jobs_fixture(),
                                  job_log("archive"), job_log("archive_provenance"))

    def test_strict_file_parsers_reject_duplicates_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "duplicate.json"
            p.write_text('{"id":1,"id":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "S0_DUPLICATE_JSON_KEY"):
                m._json(p)
            p.write_text('{"n":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "S0_NONFINITE_JSON"):
                m._json(p)
            l = Path(tmp) / "job.log"
            l.write_text("synthetic log", encoding="utf-8")
            symlink = Path(tmp) / "link.log"
            symlink.symlink_to(l)
            with self.assertRaisesRegex(ValueError, "S0_JOB_LOG_UNSAFE"):
                m._log(symlink)

    def test_ansi_escape_removed_before_log_assertions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log"
            path.write_text("\x1b[36;1m" + job_log("archive") + "\x1b[0m",
                            encoding="utf-8")
            text = m._log(path)
            self.assertNotIn("\x1b", text)
            r = m._confirm_log(text, sha=m.ARCHIVE_SHA, job="archive",
                               paths=m.ARCHIVE_PATHS)
            self.assertTrue(r["main_push_logged"])


if __name__ == "__main__":
    unittest.main()
