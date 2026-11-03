"""Conservative, read-only preflight for protecting the football repo's main branch.

This is an inventory of *potential* repository writers, not a proof that
all writes were discovered or that GitHub branch rules are enforced.
No GitHub API calls, credentials, market requests, mutations, or paid data.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PERMISSION_WRITE = re.compile(r"(?m)^\s*contents\s*:\s*write\b")
INLINE_WRITE = re.compile(r"\bcontents\s*:\s*write\b")
WRITE_ALL = re.compile(r"(?m)^\s*permissions\s*:\s*write-all\b")
GH_MUTATION = re.compile(r"\bgh\s+api\s+-X\s+(?:PUT|POST|PATCH|DELETE)\b", re.I)
GIT_PUSH = re.compile(r"\bgit\s+push\b")


def _indicators(source: str) -> list[str]:
    # Comments cannot grant write permissions. Retain all other lines as a
    # deliberately conservative scan, even if some are shell/heredoc text.
    active = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    hits = []
    if PERMISSION_WRITE.search(active) or INLINE_WRITE.search(active):
        hits.append("contents_write_permission")
    if WRITE_ALL.search(active):
        hits.append("write_all_permission")
    if GH_MUTATION.search(active):
        hits.append("gh_api_mutation")
    if GIT_PUSH.search(active):
        hits.append("git_push")
    return hits


def inventory(root: Path) -> dict:
    root = Path(root)
    workflow_dir = root / ".github" / "workflows"
    if workflow_dir.is_symlink() or not workflow_dir.is_dir():
        raise ValueError("workflow directory missing or symlinked")
    paths = sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")])
    if not paths:
        raise ValueError("no workflow files; refusing empty release audit")
    potential = []
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"workflow not a regular file: {path.name}")
        reasons = _indicators(path.read_text(encoding="utf-8"))
        if reasons:
            potential.append({"workflow": path.name, "indicators": reasons})
    return {
        "schema": "football-king-main-branch-writer-preflight-v1",
        "workflow_count": len(paths),
        "potential_repo_writers": potential,
        "potential_repo_writer_count": len(potential),
        "status": ("MIGRATION_REVIEW_REQUIRED" if potential
                   else "NO_STATIC_CANDIDATES_BUT_UNVERIFIED"),
        "main_branch_protection_independently_verified": False,
        "all_indirect_writes_excluded": False,
        "external_reviewer_approved": False,
        "production_recommendations": "DISABLED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--require-no-writer-candidates", action="store_true",
        help="Fail when any potential writer remains; does NOT certify release.",
    )
    args = parser.parse_args(argv)
    try:
        report = inventory(args.root)
    except (OSError, UnicodeError, ValueError) as exc:
        report = {
            "schema": "football-king-main-branch-writer-preflight-v1",
            "status": "AUDIT_FAILED",
            "error": str(exc),
            "main_branch_protection_independently_verified": False,
            "production_recommendations": "DISABLED",
        }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if args.require_no_writer_candidates and report["potential_repo_writers"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
