"""Evidence-based production readiness gate, independent of arbitrary percentages.

All claims must be externally verified. A green CI or synthetic TSA token
never constitutes production betting authorization.
"""
import json
from pathlib import Path

REQUIRED = (
    "independent_prematch_capture",
    "independent_tsa_operator_identity",
    "verified_source_issuer_identity",
    "real_heldout_calibration",
    "real_heldout_positive_ev",
    "deployment_risk_controls",
)


def assess_production_readiness(evidence):
    """Return a fail-closed readiness report from explicit audited evidence.

    Each required field must be the boolean True, not a truthy string or 1.
    This does not authenticate supplied evidence: external audit is required.
    """
    evidence = evidence if isinstance(evidence, dict) else {}
    checks = {name: "CLAIMED_VERIFIED" if type(evidence.get(name)) is bool
              and evidence[name] is True else "NOT_VERIFIED"
              for name in REQUIRED}
    missing = [name for name, status in checks.items() if status != "CLAIMED_VERIFIED"]
    return {
        "status": "HOLD",
        "checks": checks,
        "missing_evidence": missing,
        "external_audit_required": True,
        "claims_complete": not missing,
        "production_recommendations": "DISABLED",
        "completion_percentage": None,
        "note": "Unverified assertions cannot grant production admission.",
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims-json", type=Path)
    args = parser.parse_args()
    claims = {}
    if args.claims_json is not None:
        try:
            if args.claims_json.stat().st_size > 100_000:
                raise ValueError("oversized claims")
            claims = json.loads(args.claims_json.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            claims = {}
    report = assess_production_readiness(claims)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
