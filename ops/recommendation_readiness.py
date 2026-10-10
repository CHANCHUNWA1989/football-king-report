"""Fail-closed production recommendation readiness audit. No fabricated evidence."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = ("live_api_verified", "prematch_quote_fresh", "independent_model_validated",
            "time_split_backtest_passed", "forward_settled_sample_passed",
            "lineup_verified", "settlement_tracking_verified")

def audit(evidence, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(evidence, dict):
        evidence = {}
    checks = {}
    for key in REQUIRED:
        item = evidence.get(key)
        # A self-attested boolean is not verifiable proof.
        ok = (isinstance(item, dict) and item.get("passed") is True
              and isinstance(item.get("artifact_sha256"), str)
              and len(item["artifact_sha256"]) == 64
              and all(c in "0123456789abcdef" for c in item["artifact_sha256"])
              and item.get("reviewed_by") not in (None, "", "self"))
        checks[key] = {"passed": bool(ok), "reason": "EVIDENCE_REVIEW_REQUIRED" if not ok else "EVIDENCE_METADATA_PRESENT"}
    # Hash and reviewer metadata alone cannot establish actual independent validation.
    # No promotion until an authenticated verification service is implemented.
    return {"schema": "football-king-readiness-v1", "generated_utc": now.isoformat(),
            "status": "HOLD", "production_recommendations": "DISABLED",
            "reason": "TRUSTED_EVIDENCE_VERIFIER_NOT_IMPLEMENTED",
            "checks": checks, "missing_or_unverified": [k for k,v in checks.items() if not v["passed"]]}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", default="sources/recommendation_evidence.json")
    parser.add_argument("--output", default="output/recommendation_readiness.json")
    args = parser.parse_args()
    path = Path(args.evidence)
    try:
        evidence = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        evidence = {}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    report = audit(evidence)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PRODUCTION:", report["production_recommendations"], "REASON:", report["reason"])

if __name__ == "__main__":
    main()
