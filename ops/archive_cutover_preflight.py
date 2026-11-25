"""Offline P0 #569 inventory: report legacy main writes, never clear cutover.

Static workflow inspection is NOT a complete repository audit or a deploy
gate. It can prove known unsafe commands remain; their absence is UNKNOWN,
not evidence of migration or an authorization to enable Rulesets.
No network, Git writes, branch changes, token usage, or automatic promotion.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re

MAX_WORKFLOW_BYTES = 1_000_000
_JOB = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(?:#.*)?$", re.M)
_MAIN_PUSH = re.compile(
    r"\bgit(?:\s+-C\s+(?:\"[^\"]+\"|'[^']+'|\S+))?"
    r"\s+push\s+origin\s+HEAD:refs/heads/main\b"
)
_SETTLED_PUT = re.compile(
    r"\bgh\s+api\s+-X\s+PUT\s+[^\n]*contents/evidence/settled\.json\b"
)
_READ_MARKERS = (
    "evidence/settled.json",
    "forecast_provenance/",
    "research_pairs/",
    "history/",
)


class CutoverAuditHold(ValueError):
    """Safe, bounded diagnostic rejection."""


def _jobs(workflow):
    matches = list(_JOB.finditer(workflow))
    jobs_match = re.search(r"^jobs:[ \t]*$", workflow, re.M)
    if jobs_match is None:
        raise CutoverAuditHold("WORKFLOW_JOBS_UNVERIFIABLE")
    matches = [m for m in matches if m.start() > jobs_match.end()]
    if not matches:
        raise CutoverAuditHold("WORKFLOW_JOBS_UNVERIFIABLE")
    return {
        m.group(1): workflow[m.end() : matches[i + 1].start()
                            if i + 1 < len(matches) else len(workflow)]
        for i, m in enumerate(matches)
    }


def inspect(workflow):
    """Return a fail-closed evidence *inventory*, never a READY decision."""
    if not isinstance(workflow, str) or not workflow.strip():
        raise CutoverAuditHold("WORKFLOW_INPUT_UNVERIFIABLE")
    jobs = _jobs(workflow)
    # Strip only whole-line comments; this is not a shell AST or an exhaustive
    # enumeration of indirect writes. Any ambiguity is always HOLD.
    live = {
        name: "\n".join(line for line in body.splitlines()
                        if not line.lstrip().startswith("#"))
        for name, body in jobs.items()
    }
    writers = sorted(name for name, body in live.items()
                     if _MAIN_PUSH.search(body))
    put_jobs = sorted(name for name, body in live.items()
                      if _SETTLED_PUT.search(body))
    write_permission_jobs = sorted(
        name for name, body in live.items()
        if re.search(r"(?m)^[ \t]+contents:[ \t]*write[ \t]*$", body)
    )
    required = {"archive_provenance", "archive"}
    missing = sorted(required.difference(jobs))
    if missing:
        status = "HOLD_REQUIRED_ARCHIVE_JOB_UNVERIFIABLE"
    elif writers or put_jobs:
        status = "HOLD_LEGACY_MAIN_WRITERS_PRESENT"
    else:
        status = "HOLD_MIGRATION_NOT_INDEPENDENTLY_VERIFIED"
    return {
        "status": status,
        "legacy_direct_main_push_jobs": writers,
        "legacy_settled_contents_put_jobs": put_jobs,
        "contents_write_permission_jobs": write_permission_jobs,
        "required_jobs_not_found": missing,
        "read_path_markers_in_workflow": [
            marker for marker in _READ_MARKERS if marker in workflow
        ],
        "inventory_exhaustive": False,
        "archive_branch_live_canary_verified": False,
        "downstream_read_parity_verified": False,
        "independent_review_verified": False,
        "ruleset_activation_authorized": False,
        "production_recommendations": "DISABLED",
    }


def inspect_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise CutoverAuditHold("UNSAFE_OR_MISSING_WORKFLOW")
    try:
        if not 0 < path.stat().st_size <= MAX_WORKFLOW_BYTES:
            raise CutoverAuditHold("WORKFLOW_SIZE_UNVERIFIABLE")
        data = path.read_bytes()
        workflow = data.decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise CutoverAuditHold("WORKFLOW_READ_UNVERIFIABLE") from exc
    receipt = inspect(workflow)
    receipt["workflow_sha256"] = hashlib.sha256(data).hexdigest()
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = inspect_file(args.workflow)
    except (CutoverAuditHold, OSError, ValueError):
        print(json.dumps({"status": "HOLD_WORKFLOW_INVENTORY_UNVERIFIABLE",
                          "ruleset_activation_authorized": False,
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    # Always non-zero by design: this research inventory never grants cutover.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
