"""Research-only static inventory of ALL checked-in Actions workflow files.

Never authorizes Ruleset activation, production releases, or betting.
Only literal YAML/text hints are inventoried: no shell AST, action source
inspection, full repository coverage or authenticated GitHub controls.
No network or write operations are performed.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re

MAX_FILE_BYTES = 1_000_000
MAX_FLEET_BYTES = 8_000_000
MAX_WORKFLOWS = 128

_GIT_PUSH = re.compile(
    r"\bgit(?:\s+-C\s+(?:\"[^\"]+\"|'[^']+'|\S+))?\s+push\b"
)
_DIRECT_MAIN = re.compile(
    r"\bgit(?:\s+-C\s+(?:\"[^\"]+\"|'[^']+'|\S+))?\s+push"
    r"\s+origin\s+HEAD:refs/heads/main\b"
)
_GH_API_MUTATION = re.compile(
    r"\bgh\s+api\s+(?:-X|--method)\s+(?:PUT|POST|PATCH|DELETE)\b",
    re.IGNORECASE,
)
_GH_CONTENTS_MUTATION = re.compile(
    r"\bgh\s+api\s+(?:-X|--method)\s+(?:PUT|POST|PATCH|DELETE)"
    r"\s+[^\n]*\bcontents/",
    re.IGNORECASE,
)
_CONTENTS_WRITE = re.compile(r"^\s*contents:\s*write(?:\s*(?:#.*)?)?$")
_SHELL_MUTATION = re.compile(
    r"\b(?:curl|wget)\b.*(?:-X|--request)\s+(?:PUT|POST|PATCH|DELETE)\b",
    re.IGNORECASE,
)
_SCRIPT_ACTION = re.compile(r"uses:\s*actions/github-script@", re.IGNORECASE)


class WorkflowFleetHold(ValueError):
    """Fail closed without exposing source lines or repository credentials."""


def _line_numbers(source, pattern):
    return [number for number, line in enumerate(source.splitlines(), 1)
            if not line.lstrip().startswith("#") and pattern.search(line)]


def inventory(directory):
    """Return deterministic read-only risk indicators for every local YAML file."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise WorkflowFleetHold("MISSING_OR_UNSAFE_WORKFLOW_DIRECTORY")
    entries = sorted(directory.iterdir(), key=lambda p: p.name)
    if any(e.is_symlink() or not e.is_file() for e in entries):
        raise WorkflowFleetHold("UNSAFE_WORKFLOW_DIRECTORY_ENTRY")
    files = [p for p in entries if p.suffix.lower() in (".yml", ".yaml")]
    if not 0 < len(files) <= MAX_WORKFLOWS:
        raise WorkflowFleetHold("UNVERIFIABLE_WORKFLOW_COUNT")
    results = []
    total = 0
    for item in files:
        try:
            size = item.stat().st_size
            if not 0 < size <= MAX_FILE_BYTES:
                raise WorkflowFleetHold("WORKFLOW_SIZE_LIMIT")
            total += size
            if total > MAX_FLEET_BYTES:
                raise WorkflowFleetHold("WORKFLOW_FLEET_SIZE_LIMIT")
            raw = item.read_bytes()
            source = raw.decode("utf-8", errors="strict")
        except (OSError, UnicodeError) as exc:
            raise WorkflowFleetHold("WORKFLOW_READ_NOT_VERIFIED") from exc
        entry = {
            "workflow": item.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "contents_write_permission_lines": _line_numbers(source, _CONTENTS_WRITE),
            "git_push_lines": _line_numbers(source, _GIT_PUSH),
            "direct_main_push_lines": _line_numbers(source, _DIRECT_MAIN),
            "gh_api_mutation_lines": _line_numbers(source, _GH_API_MUTATION),
            "contents_api_mutation_lines": _line_numbers(source, _GH_CONTENTS_MUTATION),
            "shell_api_mutation_lines": _line_numbers(source, _SHELL_MUTATION),
            "github_script_action_lines": _line_numbers(source, _SCRIPT_ACTION),
        }
        if any(entry[key] for key in entry if key.endswith("_lines")):
            results.append(entry)
    def names(field):
        return [entry["workflow"] for entry in results if entry[field]]
    return {
        "status": "HOLD_WORKFLOW_FLEET_CUTOVER_UNVERIFIED",
        "workflow_files_scanned": len(files),
        "scanned_directory": ".github/workflows",
        "total_workflow_bytes": total,
        "explicit_main_git_push_workflows": names("direct_main_push_lines"),
        "contents_api_mutation_workflows": names("contents_api_mutation_lines"),
        "gh_api_mutation_workflows": names("gh_api_mutation_lines"),
        "git_push_workflows": names("git_push_lines"),
        "contents_write_permission_workflows": names("contents_write_permission_lines"),
        "suspected_write_or_dynamic_action_indicators": results,
        "workflow_directory_inventory_complete": True,
        "repository_writer_inventory_exhaustive": False,
        "external_action_implementations_audited": False,
        "other_script_and_reusable_workflow_writes_audited": False,
        "authenticated_remote_archive_canary_verified": False,
        "human_review_verified": False,
        "main_ruleset_activation_authorized": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows", type=Path,
                        default=Path(".github/workflows"))
    args = parser.parse_args(argv)
    try:
        receipt = inventory(args.workflows)
    except (WorkflowFleetHold, ValueError, OSError):
        receipt = {
            "status": "HOLD_WORKFLOW_FLEET_INVENTORY_FAILED",
            "main_ruleset_activation_authorized": False,
            "production_recommendations": "DISABLED",
        }
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    # This is an evidence inventory, never a release gate that can pass.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
