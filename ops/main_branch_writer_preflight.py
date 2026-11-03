"""Conservative, read-only repository writer/reader preflight.

Scan workflows plus *directly referenced* ops Python scripts for potential
mutations and shared data paths. Every edge is a candidate for manual review,
NOT proof of an actual writer/consumer relationship or secure branch rule.
No GitHub API, credentials, paid market calls, mutations, or remote access.
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
GIT_PUSH = re.compile(r"\bgit(?:\s+-C\s+\S+)?\s+push\b")
DIRECT_MAIN_PUSH = re.compile(r"\bpush\s+origin\s+HEAD:refs/heads/main\b")
CONTENTS_API_WRITE = re.compile(
    r"""\bgh\s+api\s+-X\s+(?:PUT|POST|PATCH|DELETE)\s+["']?repos/\$GITHUB_REPOSITORY/contents/""",
    re.I,
)
ARTIFACT_API_DELETE = re.compile(r"""\bgh\s+api\s+-X\s+DELETE\s+["']?\$artifact_path\b""", re.I)
# Literal data paths can be read *or* written. Never infer direction from a path.
DATA_PATH = re.compile(
    r"(?<![A-Za-z0-9_])(?:sources|market|evidence|reports|history|"
    r"research_pairs|research_quality|research_reports|forecast_provenance|"
    r"ndr_capture_provenance|openliga_capture_provenance|"
    r"shadow|worldwide_shadow)/[A-Za-z0-9_./-]+"
)
OPS_SCRIPT = re.compile(r"(?<![A-Za-z0-9_])ops/[A-Za-z0-9_./-]+\.py\b")
MAX_SCAN_BYTES = 1_500_000


def _active(source: str) -> str:
    # Intentionally conservative: the parser is not a YAML/shell interpreter.
    # Only full-line comments are dropped; inline comments can false-positive.
    return "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))


def _indicators(source: str) -> list[str]:
    active = _active(source)
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


def _paths(source: str) -> list[str]:
    return sorted({m.group().rstrip("/.") for m in DATA_PATH.finditer(_active(source))}
                  - {""})


def _scripts(source: str) -> list[str]:
    return sorted({m.group() for m in OPS_SCRIPT.finditer(_active(source))})


def _safe_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"not a regular file: {path}")
    if path.stat().st_size > MAX_SCAN_BYTES:
        raise ValueError(f"file too large for safe inventory: {path}")
    return path.read_text(encoding="utf-8")


def inventory(root: Path) -> dict:
    root = Path(root)
    workflow_dir = root / ".github" / "workflows"
    if workflow_dir.is_symlink() or not workflow_dir.is_dir():
        raise ValueError("workflow directory missing or symlinked")
    workflows = sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")])
    if not workflows:
        raise ValueError("no workflow files; refusing empty release audit")

    potential = []
    contents_mutation_candidates = []
    artifact_delete_only = []
    details = []
    referenced_scripts = set()
    for path in workflows:
        source = _safe_text(path)
        reasons = _indicators(source)
        explicit_paths = _paths(source)
        scripts = _scripts(source)
        referenced_scripts.update(scripts)
        details.append({
            "workflow": path.name,
            "data_path_mentions": explicit_paths,
            "direct_ops_script_mentions": scripts,
        })
        if reasons:
            active = _active(source)
            explicit_mutations = []
            if DIRECT_MAIN_PUSH.search(active):
                explicit_mutations.append("explicit_main_git_push")
            if CONTENTS_API_WRITE.search(active):
                explicit_mutations.append("contents_api_mutation_branch_review_needed")
            if ARTIFACT_API_DELETE.search(active):
                explicit_mutations.append("actions_artifact_delete")
            entry = {"workflow": path.name, "indicators": reasons,
                     "mutation_scope_markers": explicit_mutations,
                     "data_path_mentions_not_proven_targets": explicit_paths,
                     "direct_ops_script_mentions": scripts}
            potential.append(entry)
            if any(x in explicit_mutations for x in
                   ("explicit_main_git_push",
                    "contents_api_mutation_branch_review_needed")):
                contents_mutation_candidates.append(path.name)
            if explicit_mutations == ["actions_artifact_delete"]:
                artifact_delete_only.append(path.name)

    by_workflow = {d["workflow"]: set(d["data_path_mentions"]) for d in details}
    overlap = []
    for writer in potential:
        w = writer["workflow"]
        for other in details:
            r = other["workflow"]
            if w == r:
                continue
            shared = sorted(by_workflow[w] & by_workflow[r])
            if shared:
                overlap.append({
                    "possible_writer_workflow": w,
                    "possible_reader_or_peer_workflow": r,
                    "shared_path_mentions_not_verified_direction": shared,
                })

    # These are directly workflow-referenced scripts only; script-to-script
    # imports, dynamic CLI invocations, API access via libraries, and PAT-based
    # permissions require manual inspection. Missing script is not silently
    # ignored because it could conceal a dynamic code path.
    scripts_scanned = []
    for name in sorted(referenced_scripts):
        source_path = root / name
        if not source_path.is_file():
            raise ValueError(f"referenced ops script missing: {name}")
        code = _safe_text(source_path)
        indicators = _indicators(code)
        scripts_scanned.append({
            "path": name,
            "mutation_markers": [i for i in indicators
                                 if i in ("gh_api_mutation", "git_push")],
            "data_path_mentions": _paths(code),
        })

    indirect_script_candidates = [s for s in scripts_scanned
                                  if s["mutation_markers"]]
    return {
        "schema": "football-king-main-branch-writer-preflight-v2",
        "workflow_count": len(workflows),
        "potential_repo_writers": potential,
        "potential_repo_writer_count": len(potential),
        "explicit_content_mutation_workflow_candidates":
            sorted(contents_mutation_candidates),
        "explicit_content_mutation_workflow_candidate_count":
            len(contents_mutation_candidates),
        "artifact_delete_only_workflow_candidates": sorted(artifact_delete_only),
        "artifact_delete_only_workflow_candidate_count": len(artifact_delete_only),
        "candidate_cross_workflow_path_overlaps": overlap,
        "candidate_cross_workflow_path_overlap_count": len(overlap),
        "direct_ops_scripts_scanned": len(scripts_scanned),
        "direct_ops_script_mutation_candidates": indirect_script_candidates,
        "direct_ops_script_mutation_candidate_count": len(indirect_script_candidates),
        "scan_coverage": "WORKFLOW_FILES_AND_DIRECTLY_MENTIONED_OPS_PYTHON_ONLY",
        "consumer_directions_and_write_targets_verified": False,
        "all_indirect_writes_excluded": False,
        "main_branch_protection_independently_verified": False,
        "external_reviewer_approved": False,
        "status": ("MIGRATION_REVIEW_REQUIRED" if potential
                   else "NO_STATIC_CANDIDATES_BUT_UNVERIFIED"),
        "production_recommendations": "DISABLED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--require-no-writer-candidates", action="store_true",
        help="Fail when any potential writer remains; does NOT certify release.",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Write report locally using exclusive creation; never overwrites.",
    )
    args = parser.parse_args(argv)
    try:
        report = inventory(args.root)
        payload = json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as file:
                file.write(payload)
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({
            "schema": "football-king-main-branch-writer-preflight-v2",
            "status": "AUDIT_FAILED",
            "error": str(exc),
            "main_branch_protection_independently_verified": False,
            "production_recommendations": "DISABLED",
        }, ensure_ascii=False, sort_keys=True))
        return 2
    print(payload, end="")
    if args.require_no_writer_candidates and report["potential_repo_writers"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
