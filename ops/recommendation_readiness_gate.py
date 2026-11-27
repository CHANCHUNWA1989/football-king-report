"""Research-only, offline recommendation readiness gate.

Never infer predictive skill from bookmaker quote availability or CI success.
This module only evaluates explicitly supplied evidence metadata.
"""
import argparse
import json
from pathlib import Path


def _valid_scope(scope):
    """Accept exact competition IDs and explicitly disjoint fixture cohorts."""
    if not isinstance(scope, dict) or set(scope) != {"competition_id", "cohort"}:
        return False
    competition = scope["competition_id"]
    return (
        isinstance(competition, str)
        and 0 < len(competition) <= 120
        and competition == competition.strip()
        and scope["cohort"] in ("league", "group_stage", "cross_group_knockout")
    )


def evaluate(evidence):
    """Check scope when supplied while accepting existing unscoped inputs.

    Scoped callers must supply both the target scope and the scope of the
    settled validation. This compares declared metadata only.
    """
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
    if "prediction_scope" in evidence or "validation_scope" in evidence:
        prediction_scope = evidence.get("prediction_scope")
        validation_scope = evidence.get("validation_scope")
        checks["validation_scope_matches_prediction"] = (
            _valid_scope(prediction_scope)
            and _valid_scope(validation_scope)
            and prediction_scope == validation_scope
        )
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
