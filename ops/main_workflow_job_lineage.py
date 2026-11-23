"""S0: correlate a historical GitHub Actions run, job logs and actual main commits.

Strict read-only, *pinned-run* acceptance. Input JSON/job logs are captured
using minimal-read-scope GitHub API access in Actions; this file never calls
GitHub, uses tokens, mutates Git, or trusts log text as executable code.

This verifies two *specific* real main writes. It cannot identify all dynamic
writers, establish third-party attestation or approve a release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

REPOSITORY = "CHANCHUNWA1989/football-king-report"
RUN_ID = 41603036531
RUN_HEAD = "ed576e4a744b129d68e85d6f07a5a0ef5676eb7f"
WORKFLOW_NAME = "Football King V4.1 iPhone Daily Report"
ARCHIVE_SHA = "73ebf27610c501c971dffa56aac0f681bf300f6f"
PROVENANCE_SHA = "d72090777c7b084e6f20dd5bba19b27225997dcf"
JOBS = {"archive": 125806924489, "archive_provenance": 125807102939}
RUN_PREFIX = "41603036531-1"
ARCHIVE_PATHS = sorted(
    f"{p}/2026/11/03/{RUN_PREFIX}.json.gz" for p in
    ("history", "research_pairs", "shadow", "verification_slates",
     "worldwide_shadow")
)
PROVENANCE_PATHS = sorted(
    f"forecast_provenance/2026/11/03/{RUN_PREFIX}/{file}" for file in (
        "negative_checks.json.gz", "paired.json.gz",
        "paired.verification.json.gz", "research.sigstore.json.gz",
        "shadow.json.gz", "shadow.verification.json.gz",
        "slate.json.gz", "slate.verification.json.gz",
        "tampered.rejection.log.gz", "wrong-source.rejection.log.gz")
)
MAX_JSON_BYTES = 250_000
MAX_LOG_BYTES = 2_000_000
SHA = re.compile(r"[0-9a-f]{40}\Z")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("S0_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _json(path: Path):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("S0_METADATA_UNSAFE")
    return json.loads(p.read_text(encoding="utf-8"),
                      object_pairs_hook=_unique_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("S0_NONFINITE_JSON")))


def _log(path: Path) -> str:
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("S0_JOB_LOG_UNSAFE")
    raw = p.read_bytes()
    # Github Actions color formatting is not part of a Git commit identity.
    text = raw.decode("utf-8", errors="strict")
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotepath=false", *args],
        text=True, capture_output=True, timeout=15, check=False)
    if result.returncode or len(result.stdout) > 150000:
        raise ValueError("S0_GIT_EVIDENCE_UNAVAILABLE")
    return result.stdout.strip()


def _run_metadata(run: dict, jobs: dict) -> dict:
    if not isinstance(run, dict) or not isinstance(jobs, dict):
        raise ValueError("S0_RUN_METADATA_NOT_OBJECT")
    if (run.get("id") != RUN_ID or run.get("name") != WORKFLOW_NAME or
        run.get("head_branch") != "main" or
        run.get("head_sha") != RUN_HEAD or
        run.get("run_attempt") != 1 or
        run.get("status") != "completed" or
        run.get("conclusion") != "success" or
        run.get("event") not in ("schedule", "workflow_run")):
        raise ValueError("S0_WRONG_WORKFLOW_RUN")
    repo = run.get("repository")
    if not isinstance(repo, dict) or repo.get("full_name") != REPOSITORY:
        raise ValueError("S0_RUN_REPOSITORY_MISMATCH")
    rows = jobs.get("jobs")
    if (not isinstance(rows, list) or not rows or
        jobs.get("total_count") != len(rows)):
        # This historical run has fewer than the 100 first-page jobs.
        # Never silently trust truncated/incomplete job metadata.
        raise ValueError("S0_INCOMPLETE_JOBS_RESPONSE")
    found = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise ValueError("S0_JOB_METADATA_INVALID")
        name = row["name"]
        if name not in JOBS:
            continue
        if (name in found or row.get("id") != JOBS[name] or
            row.get("run_id") != RUN_ID or
            row.get("status") != "completed" or
            row.get("conclusion") != "success"):
            raise ValueError("S0_JOB_ID_OR_RESULT_MISMATCH")
        found[name] = row["id"]
    if set(found) != set(JOBS):
        raise ValueError("S0_REQUIRED_ARCHIVE_JOBS_MISSING")
    return found


def _confirm_log(log: str, *, sha: str, job: str, paths: list[str]) -> dict:
    short = sha[:7]
    if (f"[detached HEAD {short}]" not in log or
        "HEAD -> main" not in log or
        "To https://github.com/" + REPOSITORY not in log or
        f"run {RUN_ID}" not in log or
        any(path not in log for path in paths)):
        raise ValueError("S0_JOB_LOG_COMMIT_PATH_OR_PUSH_UNVERIFIED")
    # Attribution is to a *specific job's observed log*; do not infer
    # everything ever written by this workflow or who held credentials.
    if job not in JOBS:
        raise ValueError("S0_JOB_NAME_NOT_PINNED")
    return {
        "job_name": job,
        "job_id": JOBS[job],
        "commit_sha": sha,
        "main_push_logged": True,
        "log_contains_all_changed_paths": True,
        "sanitized_log_sha256": hashlib.sha256(log.encode("utf-8")).hexdigest(),
        "job_identity_proof_scope": "MATCHED_THIS_RUN_JOB_LOG_ONLY",
    }


def corroborate(root: Path, run: dict, jobs: dict,
                archive_log: str, provenance_log: str) -> dict:
    found = _run_metadata(run, jobs)
    main = Path(root)
    if main.is_symlink() or not main.is_dir():
        raise ValueError("S0_MAIN_CHECKOUT_UNSAFE")
    if _git(main, "symbolic-ref", "--quiet", "--short", "HEAD") != "main":
        raise ValueError("S0_NOT_ON_MAIN_BRANCH")
    head = _git(main, "rev-parse", "--verify", "HEAD")
    if not SHA.fullmatch(head):
        raise ValueError("S0_INVALID_MAIN_SHA")
    records = []
    for job, commit, parent, expected, log in [
        ("archive", ARCHIVE_SHA, RUN_HEAD, ARCHIVE_PATHS, archive_log),
        ("archive_provenance", PROVENANCE_SHA, ARCHIVE_SHA,
         PROVENANCE_PATHS, provenance_log),
    ]:
        if _git(main, "rev-parse", f"{commit}^") != parent:
            raise ValueError("S0_ARCHIVE_COMMIT_PARENT_MISMATCH")
        listed = _git(main, "diff-tree", "--root", "--no-commit-id",
                      "--name-only", "--no-renames", "-r", commit).splitlines()
        if sorted(listed) != expected:
            raise ValueError("S0_ARCHIVE_COMMIT_CHANGED_FILES_MISMATCH")
        if subprocess.run(
            ["git", "-C", str(main), "merge-base", "--is-ancestor",
             commit, head], capture_output=True, timeout=15
        ).returncode:
            raise ValueError("S0_ARCHIVE_COMMIT_NOT_IN_MAIN")
        row = _confirm_log(log, sha=commit, job=job, paths=expected)
        row["commit_parent_sha"] = parent
        row["git_changed_paths"] = expected
        row["source_provider_independently_attested"] = False
        records.append(row)
    return {
        "schema": "football-king-s0-main-workflow-job-correspondence-v1",
        "status": "TWO_HISTORICAL_MAIN_WRITER_JOBS_CORROBORATED",
        "repository": REPOSITORY,
        "run_id": RUN_ID,
        "run_head_sha": RUN_HEAD,
        "main_checkout_head_sha": head,
        "jobs_checked": found,
        "historical_commit_job_pairs": records,
        "verified_scope": "ONE_PUBLIC_HISTORICAL_WORKFLOW_RUN_TWO_JOBS",
        "all_main_writers_identified": False,
        "all_dynamic_reader_edges_checked": False,
        "github_branch_protection_enforced": False,
        "independent_reviewer_approved": False,
        "independent_external_timing_verified": False,
        "real_bsd_archive_cutover_completed": False,
        "permission_to_merge_or_deploy": False,
        "verified_positive_ev": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--main-checkout", required=True, type=Path)
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--jobs", required=True, type=Path)
    p.add_argument("--archive-log", required=True, type=Path)
    p.add_argument("--provenance-log", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        result = corroborate(args.main_checkout, _json(args.run), _json(args.jobs),
                             _log(args.archive_log), _log(args.provenance_log))
        with args.output.open("x", encoding="utf-8") as out:
            json.dump(result, out, indent=2, sort_keys=True)
            out.write("\n")
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as exc:
        # Never echo untrusted job logs, tokens, paths or server errors.
        codes = {
            "S0_RUN_METADATA_NOT_OBJECT", "S0_WRONG_WORKFLOW_RUN",
            "S0_RUN_REPOSITORY_MISMATCH", "S0_INCOMPLETE_JOBS_RESPONSE",
            "S0_JOB_METADATA_INVALID", "S0_JOB_ID_OR_RESULT_MISMATCH",
            "S0_REQUIRED_ARCHIVE_JOBS_MISSING", "S0_MAIN_CHECKOUT_UNSAFE",
            "S0_NOT_ON_MAIN_BRANCH", "S0_INVALID_MAIN_SHA",
            "S0_ARCHIVE_COMMIT_PARENT_MISMATCH",
            "S0_ARCHIVE_COMMIT_CHANGED_FILES_MISMATCH",
            "S0_ARCHIVE_COMMIT_NOT_IN_MAIN",
            "S0_JOB_LOG_COMMIT_PATH_OR_PUSH_UNVERIFIED", "S0_JOB_NAME_NOT_PINNED",
            "S0_METADATA_UNSAFE", "S0_JOB_LOG_UNSAFE", "S0_DUPLICATE_JSON_KEY",
            "S0_NONFINITE_JSON", "S0_GIT_EVIDENCE_UNAVAILABLE",
        }
        message = str(exc)
        print(json.dumps({
            "status": "S0_JOB_ATTRIBUTION_UNVERIFIED",
            "error_code": message if message in codes else "REDACTED",
            "production_recommendations": "DISABLED",
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "status": result["status"], "run_id": result["run_id"],
        "main_checkout_head_sha": result["main_checkout_head_sha"],
        "matched_jobs": list(result["jobs_checked"]),
        "matched_commits": [x["commit_sha"] for x in
                            result["historical_commit_job_pairs"]],
        "all_main_writers_identified": False,
        "independent_reviewer_approved": False,
        "production_recommendations": "DISABLED",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
