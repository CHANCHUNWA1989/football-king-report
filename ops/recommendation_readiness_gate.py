"""Research-only, offline recommendation readiness gate.

Never infer predictive skill from bookmaker quote availability or CI success.
This module only evaluates explicitly supplied evidence metadata.
"""
import argparse
import json
from pathlib import Path


def evaluate(evidence):
    if not isinstance(evidence, dict):
        raise ValueError("INVALID_EVIDENCE")
    checks = {
        "verified_complete_three_market_quotes": evidence.get(
            "verified_complete_three_market_quotes") is True,
        "independent_pre_match_forecasts": evidence.get(
            "independent_pre_match_forecasts") is True,
        "settled_out_of_sample_validation": evidence.get(
            "settled_out_of_sample_validation") is True,
        "calibration_and_leakage_review": evidence.get(
            "calibration_and_leakage_review") is True,
        "human_approval": evidence.get("human_approval") is True,
    }
    return {
        "schema": "football-king-readiness-gate-v1",
        "checks": checks,
        "unmet_requirements": [k for k, v in checks.items() if not v],
        "evidence_all_checks_met": all(checks.values()),
        # This is an evidence checklist, never a switch for live recommendations.
        "production_recommendations": "DISABLED",
        "status": "EVIDENCE_REVIEW" if all(checks.values()) else "HOLD",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", default="market/recommendation_readiness.json")
    args = p.parse_args()
    evidence = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = evaluate(evidence)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(json.dumps({"status": report["status"],
                      "unmet_requirements": report["unmet_requirements"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
