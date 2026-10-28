"""Fail-closed, deterministic task ledger for independently executed agent work.

This module schedules *descriptions* of work. It does not pretend to run
external AI agents, call providers, or approve betting recommendations.
"""
import json
from pathlib import Path

SCHEMA = "football-king-agent-task-ledger-v1"
TASKS = (
    ("provider_data", (), "Verify licensed match, odds and data provenance"),
    ("lineups_tactics", ("provider_data",), "Validate official XI and tactical evidence"),
    ("model_evaluation", ("provider_data",), "Evaluate out-of-sample 1X2/totals/spreads"),
    ("independent_review", ("lineups_tactics", "model_evaluation"), "Independently review evidence"),
    ("release_review", ("independent_review",), "Review CI and release readiness"),
)
VALID = frozenset(("PENDING", "BLOCKED", "RUNNING", "EVIDENCE_SUBMITTED", "VERIFIED", "FAILED"))


def plan(evidence=None):
    evidence = evidence if isinstance(evidence, dict) else {}
    verified = set()
    tasks = []
    for task_id, depends_on, description in TASKS:
        item = evidence.get(task_id)
        # A self-reported success is NOT independent verification.
        signed = (isinstance(item, dict)
                  and item.get("independent_review_verified") is True
                  and isinstance(item.get("evidence_ref"), str)
                  and item["evidence_ref"].startswith("github://")
                  and item.get("source_authenticated") is True)
        if signed and all(dep in verified for dep in depends_on):
            state = "EVIDENCE_SUBMITTED"
        elif all(dep in verified for dep in depends_on):
            state = "PENDING"
        else:
            state = "BLOCKED"
        tasks.append({"task_id": task_id, "depends_on": list(depends_on),
                      "description": description, "state": state,
                      "execution": "NOT_STARTED",
                      "external_agent_invoked": False})
        # No task is automatically marked VERIFIED from user-supplied JSON.
    return {
        "schema": SCHEMA,
        "mode": "PLANNING_ONLY",
        "tasks": tasks,
        "verified_task_count": len(verified),
        "independent_agent_execution_confirmed": False,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "automatic_bets": False,
    }


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--evidence")
    args = p.parse_args(argv)
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8")) if args.evidence else None
    report = plan(evidence)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "tasks": len(report["tasks"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
