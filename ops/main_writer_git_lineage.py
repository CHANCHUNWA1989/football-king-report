"""S0 evidence: read *actual* main Git history, without changing any refs.

Run from the PR's trusted code checkout against a separately checked-out
main worktree. Changed Git paths prove modifications, not which workflow,
credential, provider or person wrote them. Never certify release from this.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_COMMITS = 120
MAX_FILES_PER_COMMIT = 100000
MAX_TOTAL_CHANGED_PATHS = 200000
MAX_RECORDED_MATCHING_PATHS_PER_COMMIT = 1000

INTERESTING_EXACT = {
    "sources/bsd_status_latest.json": "BSD_STATUS_MAIN_WRITE",
    "sources/bsd_market_latest.json": "BSD_MARKET_MAIN_WRITE",
    "sources/latest.json": "SECONDARY_SOURCE_MAIN_WRITE",
    "market/latest.json": "MARKET_RESEARCH_MAIN_WRITE",
    "evidence/settled.json": "LEGACY_SETTLEMENT_MAIN_WRITE",
}
INTERESTING_PREFIX = {
    "history/": "RESEARCH_HISTORY_MAIN_WRITE",
    "forecast_provenance/": "FORECAST_PROVENANCE_MAIN_WRITE",
    "research_pairs/": "RESEARCH_PAIRS_MAIN_WRITE",
    "shadow/": "RESEARCH_SHADOW_MAIN_WRITE",
    "worldwide_shadow/": "WORLDWIDE_SHADOW_MAIN_WRITE",
    "verification_slates/": "VERIFICATION_SLATES_MAIN_WRITE",
    "sources/": "OTHER_SOURCE_MAIN_WRITE",
    "market/": "OTHER_MARKET_MAIN_WRITE",
    "evidence/": "OTHER_EVIDENCE_MAIN_WRITE",
    "ndr_capture_provenance/": "NDR_PROVENANCE_MAIN_WRITE",
    "openliga_capture_provenance/": "OPENLIGA_PROVENANCE_MAIN_WRITE",
}


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotepath=false", *args],
        capture_output=True, text=True, encoding="utf-8",
        timeout=15, check=False,
    )
    if proc.returncode:
        raise ValueError("MAIN_GIT_QUERY_FAILED")
    if len(proc.stdout) > 12_000_000:
        raise ValueError("MAIN_GIT_OUTPUT_OVERSIZE")
    return proc.stdout.strip()


def classify(path: str) -> str | None:
    if path in INTERESTING_EXACT:
        return INTERESTING_EXACT[path]
    for prefix, label in INTERESTING_PREFIX.items():
        if path.startswith(prefix):
            return label
    return None


def capture(main_checkout: Path, *, max_commits: int = 60, now=None) -> dict:
    if type(max_commits) is not int or not 1 <= max_commits <= MAX_COMMITS:
        raise ValueError("INVALID_MAIN_HISTORY_LIMIT")
    root = Path(main_checkout)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("MAIN_CHECKOUT_NOT_DIRECTORY")
    if _git(root, "symbolic-ref", "--quiet", "--short", "HEAD") != "main":
        raise ValueError("NOT_CHECKED_OUT_MAIN_BRANCH")
    head = _git(root, "rev-parse", "--verify", "HEAD")
    if not SHA.fullmatch(head):
        raise ValueError("INVALID_MAIN_HEAD_SHA")
    shallow = _git(root, "rev-parse", "--is-shallow-repository") == "true"
    shas = _git(root, "rev-list", f"--max-count={max_commits}", head).splitlines()
    if not shas or len(shas) > max_commits or any(not SHA.fullmatch(x) for x in shas):
        raise ValueError("INVALID_MAIN_ANCESTRY")
    if shas[0] != head:
        raise ValueError("INCONSISTENT_MAIN_HEAD")

    matches = []
    all_observed = 0
    total_matching_paths = 0
    truncated_matching_commits = 0
    category_commits: dict[str, set[str]] = {}
    unique_paths: set[str] = set()
    for sha in shas:
        raw = _git(root, "diff-tree", "--root", "--no-commit-id", "--name-only",
                   "-r", "--no-renames", sha)
        changed = raw.splitlines() if raw else []
        if len(changed) > MAX_FILES_PER_COMMIT:
            raise ValueError("TOO_MANY_FILES_IN_ONE_COMMIT")
        all_observed += len(changed)
        if all_observed > MAX_TOTAL_CHANGED_PATHS:
            raise ValueError("MAIN_HISTORY_PATH_LIMIT_EXCEEDED")
        if any(not path or "\x00" in path or "\n" in path for path in changed):
            raise ValueError("INVALID_MAIN_CHANGED_PATH")
        unique_paths.update(changed)
        categorized = [{"path": p, "category": classify(p)}
                       for p in changed if classify(p) is not None]
        total_matching_paths += len(categorized)
        if categorized:
            listed = categorized[:MAX_RECORDED_MATCHING_PATHS_PER_COMMIT]
            is_truncated = len(listed) != len(categorized)
            if is_truncated:
                truncated_matching_commits += 1
            matches.append({
                "commit_sha": sha,
                "candidate_write_paths": listed,
                "candidate_write_path_count": len(categorized),
                "candidate_path_list_truncated": is_truncated,
                # Not a confirmed run ID, job author, reader or source identity.
                "writer_workflow_identified_from_commit": False,
            })
            for item in categorized:
                category_commits.setdefault(item["category"], set()).add(sha)

    captured = now or datetime.now(timezone.utc)
    if captured.tzinfo is None:
        raise ValueError("MAIN_AUDIT_CLOCK_NOT_TIMEZONE_AWARE")
    return {
        "schema": "football-king-main-git-runtime-lineage-v1",
        "status": "PARTIAL_REAL_MAIN_GIT_COMMIT_LINEAGE_CAPTURED",
        "captured_utc": captured.astimezone(timezone.utc).isoformat(),
        "main_head_sha": head,
        "main_branch_checkout_verified": True,
        "sampled_commit_count": len(shas),
        "shallow_checkout": shallow,
        "sampled_history_complete": not shallow and len(shas) < max_commits,
        "sampled_path_change_count": all_observed,
        "sampled_distinct_changed_path_count": len(unique_paths),
        "matching_commit_count": len(matches),
        "matching_changed_path_count": total_matching_paths,
        "matching_commit_path_lists_truncated": truncated_matching_commits,
        "full_candidate_path_lists_in_evidence": truncated_matching_commits == 0,
        "commit_path_evidence": matches,
        "main_write_path_categories": {
            category: len(commits) for category, commits
            in sorted(category_commits.items())
        },
        "concrete_git_file_changes_observed": True,
        "writer_workflow_attribution_independently_verified": False,
        "all_dynamic_writers_and_readers_audited": False,
        "branch_protection_independently_verified": False,
        "independent_reviewer_approved": False,
        "full_s0_acceptance": False,
        "permission_to_merge": False,
        "verified_positive_ev": False,
        "production_recommendations": "DISABLED",
        "note": "Path ancestry is direct Git evidence, not workflow/source identity. "
                "Limited by checkout depth and max_commits; never proves absence of writers.",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--main-checkout", type=Path, required=True)
    p.add_argument("--max-commits", type=int, default=60)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        report = capture(args.main_checkout, max_commits=args.max_commits)
        with args.output.open("x", encoding="utf-8") as dest:
            json.dump(report, dest, ensure_ascii=False, sort_keys=True, indent=2)
            dest.write("\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # Only emit our fixed, non-sensitive diagnostic codes. Never print
        # Git stderr, environment values, private URLs or path contents.
        safe_codes = {
            "INVALID_MAIN_HISTORY_LIMIT",
            "MAIN_CHECKOUT_NOT_DIRECTORY",
            "MAIN_GIT_QUERY_FAILED",
            "MAIN_GIT_OUTPUT_OVERSIZE",
            "NOT_CHECKED_OUT_MAIN_BRANCH",
            "INVALID_MAIN_HEAD_SHA",
            "INVALID_MAIN_ANCESTRY",
            "INCONSISTENT_MAIN_HEAD",
            "TOO_MANY_FILES_IN_ONE_COMMIT",
            "MAIN_HISTORY_PATH_LIMIT_EXCEEDED",
            "INVALID_MAIN_CHANGED_PATH",
            "MAIN_AUDIT_CLOCK_NOT_TIMEZONE_AWARE",
        }
        print(json.dumps({
            "status": "MAIN_RUNTIME_LINEAGE_AUDIT_INCOMPLETE",
            "error_type": type(exc).__name__,
            "error_code": str(exc) if isinstance(exc, ValueError)
                          and str(exc) in safe_codes else "REDACTED",
            "branch_protection_independently_verified": False,
            "production_recommendations": "DISABLED",
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "status": report["status"],
        "main_head_sha": report["main_head_sha"],
        "sampled_commit_count": report["sampled_commit_count"],
        "matching_commit_count": report["matching_commit_count"],
        "main_write_path_categories": report["main_write_path_categories"],
        "all_dynamic_writers_and_readers_audited": False,
        "production_recommendations": "DISABLED",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
