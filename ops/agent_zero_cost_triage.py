"""Offline, read-only Agent triage for ChatGPT Work / Codex.

Never calls an LLM, sends secrets, edits application code or enables wagers.
"""
import argparse
import json
from pathlib import Path

KNOWN = {
    "MISSING", "MISSING_COMPONENT", "OVERSIZED", "INVALID_OBJECT",
    "UNSAFE_PRODUCTION_FLAG", "MISSING_TIMESTAMP", "NAIVE_TIMESTAMP",
    "FUTURE_TIMESTAMP", "STALE", "SOURCE_NOT_READY",
    "EMPTY_MARKET_COVERAGE", "NO_MARKET_EVENTS", "EMPTY_SOURCE_COVERAGE",
    "SETTLEMENT_OLDER_THAN_48H", "INVALID_EVIDENCE",
    "INVALID_EVIDENCE_TIME", "OVERSIZED_EVIDENCE",
}
PATHS = {
    "ops/research_recommender.py", "ops/forward_validation.py",
    "ops/release_guard.py", "market/latest.json", "sources/latest.json",
    "evidence/settled.json",
}


def triage(audit):
    if not isinstance(audit, dict):
        raise ValueError("INVALID_AUDIT")
    required = {
        "schema": "football-king-agent-audit-v2",
        "mode": "SHADOW_READ_ONLY",
        "production_recommendations": "DISABLED",
        "automatic_bets": False,
        "actions_performed": [],
        "status": "HOLD",
        "next_action": "REFRESH_OR_REPAIR_INPUTS",
    }
    for key, expected in required.items():
        if type(audit.get(key)) is not type(expected) or audit[key] != expected:
            raise ValueError("UNSAFE_OR_UNEXPECTED_AUDIT")
    diagnostics = audit.get("diagnostics")
    if not isinstance(diagnostics, list) or len(diagnostics) > 1000:
        raise ValueError("INVALID_DIAGNOSTICS")
    counts = {}
    for entry in diagnostics:
        if not isinstance(entry, dict):
            continue
        component, reason = entry.get("component"), entry.get("reason")
        if component not in PATHS or reason not in KNOWN:
            continue
        counts[(component, reason)] = counts.get((component, reason), 0) + 1
    issues = [
        {"component": component, "reason": reason, "count": count}
        for (component, reason), count in sorted(counts.items())
    ]
    return {
        "schema": "football-king-agent-triage-v1",
        "mode": "READ_ONLY",
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "automatic_bets": False,
        "llm_invocations": 0,
        "automated_code_changes": 0,
        "requires_manual_codex_authorization": True,
        "issues": issues,
        "next_step": "REVIEW_AUDIT_AND_OPEN_DRAFT_PR_MANUALLY",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.stat().st_size > 2_000_000:
        raise ValueError("OVERSIZED_AUDIT")
    result = triage(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
