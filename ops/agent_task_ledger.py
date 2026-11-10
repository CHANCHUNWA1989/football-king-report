"""Fail-closed research task ledger with independently inspectable evidence.

A task is not VERIFIED by a claim in a JSON file. This module records evidence
submission and dependency blocking, not external agent execution.
"""
import argparse
import json
from pathlib import Path

SCHEMA = "football-king-agent-task-ledger-v2"
TASKS = (
    ("provider_data", (), "Verify licensed match, odds and data provenance"),
    ("lineups_tactics", ("provider_data",), "Validate official XI and tactical evidence"),
    ("model_evaluation", ("provider_data",), "Evaluate out-of-sample 1X2/totals/spreads"),
    ("independent_review", ("lineups_tactics", "model_evaluation"), "Independently review evidence"),
    ("release_review", ("independent_review",), "Review CI and release readiness"),
)


def _submitted(item):
    return (isinstance(item, dict)
            and item.get("independent_review_verified") is True
            and item.get("source_authenticated") is True
            and isinstance(item.get("evidence_ref"), str)
            and item["evidence_ref"].startswith("github://")
            and len(item["evidence_ref"]) <= 512)


def plan(evidence=None):
    evidence = evidence if isinstance(evidence, dict) else {}
    tasks = []
    for task_id, dependencies, description in TASKS:
        # No user-supplied declaration can satisfy dependency verification.
        blocked = bool(dependencies)
        state = "BLOCKED" if blocked else ("EVIDENCE_SUBMITTED" if _submitted(evidence.get(task_id)) else "PENDING")
        tasks.append({
            "task_id": task_id, "depends_on": list(dependencies),
            "description": description, "state": state,
            "evidence_ref": evidence.get(task_id, {}).get("evidence_ref")
            if _submitted(evidence.get(task_id)) and not blocked else None,
            "execution": "NOT_STARTED",
            "external_agent_invoked": False,
        })
    return {
        "schema": SCHEMA, "mode": "PLANNING_ONLY", "tasks": tasks,
        "verified_task_count": 0,
        "independent_agent_execution_confirmed": False,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "automatic_bets": False,
    }


def main(argv=None):
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
