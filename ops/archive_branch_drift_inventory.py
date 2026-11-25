"""Read-only, bounded archive-versus-main Git history drift inventory.

Research ONLY. An exact local commit comparison does not attest GitHub's remote
heads, permissions, identity, signatures, data rights or production readiness.

The program does not fetch, checkout, merge, reset, push or write any files.
Every outcome is HOLD / DISABLED, even a zero-difference comparison.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from ops.archive_remote_ref_gate import sanitized_git_env

SHA = re.compile(r"[0-9a-f]{40}\Z")
SAFE_PATH = re.compile(r"[A-Za-z0-9._/-]{1,280}\Z")
MAX_PATHS = 256
MAX_OUTPUT = 65536
IMMUTABLE_PREFIXES = (
    "forecast_provenance/", "history/", "shadow/", "research_pairs/",
    "verification_slates/", "worldwide_shadow/", "settlement_batches/",
    "ndr_capture_provenance/", "openliga_capture_provenance/",
    "market/history/", "sources/history/", "sources/bsd_history/",
    "sources/live_germany/history/", "sources/research_extensions_history/",
    "sources/six_league_quality_history/", "sources/weather_history/",
    "sources/wide/history/",
)
MUTABLE_PREFIXES = ("sources/", "market/", "reports/weekly/")
CATEGORIES = ("historical_added", "historical_mutated_or_removed",
              "mutable_publisher_change", "unclassified_change")


class ArchiveDriftHold(ValueError):
    """Predictable bounded rejection, without printing raw Git errors."""


def _git(repo, *args, accept=(0,)):
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), *args], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, errors="replace",
            timeout=20, check=False, env=sanitized_git_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ArchiveDriftHold("LOCAL_READONLY_GIT_UNAVAILABLE") from exc
    if p.returncode not in accept or len(p.stdout.encode("utf-8")) > MAX_OUTPUT:
        raise ArchiveDriftHold("LOCAL_READONLY_GIT_UNVERIFIABLE")
    return p.stdout.strip(), p.returncode


def inventory(repo, archive_sha, main_sha):
    """Fail-closed local exact-SHA comparison; never authorize a migration."""
    if not (isinstance(archive_sha, str) and isinstance(main_sha, str)
            and SHA.fullmatch(archive_sha) and SHA.fullmatch(main_sha)):
        raise ArchiveDriftHold("INVALID_PINNED_COMMIT_SHA")
    repo = Path(repo)
    if not repo.is_dir() or repo.is_symlink():
        raise ArchiveDriftHold("INVALID_LOCAL_REPOSITORY")
    top, _ = _git(repo, "rev-parse", "--show-toplevel")
    if Path(top).resolve() != repo.resolve():
        raise ArchiveDriftHold("REPOSITORY_ROOT_MISMATCH")
    for sha in (archive_sha, main_sha):
        t, _ = _git(repo, "cat-file", "-t", sha)
        if t != "commit":
            raise ArchiveDriftHold("PINNED_OBJECT_NOT_COMMIT")
    base, _ = _git(repo, "merge-base", archive_sha, main_sha)
    if not SHA.fullmatch(base):
        raise ArchiveDriftHold("NO_VERIFIED_COMMON_HISTORY")
    relation = (
        "same_commit" if archive_sha == main_sha else
        "archive_ancestor_of_main" if base == archive_sha else
        "main_ancestor_of_archive" if base == main_sha else "diverged"
    )

    # Exactly two fixed object IDs and a path terminator. No remote access.
    output, _ = _git(repo, "diff", "--name-status", "--no-renames",
                     archive_sha, main_sha, "--")
    categories = {name: [] for name in CATEGORIES}
    items = output.splitlines() if output else []
    if len(items) > MAX_PATHS:
        raise ArchiveDriftHold("DRIFT_FILE_COUNT_LIMIT")
    for line in items:
        parts = line.split("\t")
        if len(parts) != 2:
            raise ArchiveDriftHold("UNSAFE_GIT_DIFF_FORMAT")
        status, path = parts
        if (status not in ("A", "M", "D", "T")
                or not SAFE_PATH.fullmatch(path)
                or path.startswith("/") or ".." in Path(path).parts
                or path.startswith(".git/")):
            raise ArchiveDriftHold("UNSAFE_GIT_DIFF_ENTRY")
        if path.startswith(IMMUTABLE_PREFIXES):
            group = ("historical_added" if status == "A"
                     else "historical_mutated_or_removed")
        elif path.startswith(MUTABLE_PREFIXES):
            group = "mutable_publisher_change"
        else:
            group = "unclassified_change"
        categories[group].append({"path": path, "git_status": status})

    # Bounded exact names are useful for reviewer byte-parity replays, but
    # never treat a classification as authenticity or authorization.
    receipt = {
        "schema": "football-king-pinned-branch-drift-inventory-v1",
        "status": "HOLD_DRIFT_REVIEW_AND_HOSTED_POLICY_REQUIRED",
        "archive_sha": archive_sha,
        "main_sha": main_sha,
        "merge_base_sha": base,
        "relationship": relation,
        "changed_files": len(items),
        "historical_added": len(categories["historical_added"]),
        "historical_mutated_or_removed": len(categories["historical_mutated_or_removed"]),
        "mutable_publisher_change": len(categories["mutable_publisher_change"]),
        "unclassified_change": len(categories["unclassified_change"]),
        "files_by_category": categories,
        "local_snapshot_only": True,
        "actual_remote_head_verified": False,
        "source_bytes_reconciled": False,
        "branch_protection_verified": False,
        "independent_review_verified": False,
        "archive_write_authorized": False,
        "main_ruleset_activation_authorized": False,
        "production_recommendations": "DISABLED",
    }
    receipt["path_manifest_sha256"] = hashlib.sha256(json.dumps(
        categories, sort_keys=True, separators=(",", ":")
    ).encode("ascii")).hexdigest()
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--archive-sha", required=True)
    parser.add_argument("--main-sha", required=True)
    args = parser.parse_args(argv)
    try:
        report = inventory(args.repo, args.archive_sha, args.main_sha)
    except (ArchiveDriftHold, ValueError, OSError):
        print(json.dumps({
            "status": "HOLD_DRIFT_INVENTORY_NOT_VERIFIABLE",
            "production_recommendations": "DISABLED",
            "archive_write_authorized": False,
        }, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    # A detailed local comparison must never be promoted to a release pass.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
