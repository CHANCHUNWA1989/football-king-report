"""Independent-evidence checklist for football model production readiness.

This inventory is descriptive, not an authorization mechanism. A CI pass or
self-asserted JSON field must never unlock betting recommendations.
"""
from pathlib import Path
import json

CHECKS = {
    "independent_prematch_capture": {
        "required": "Immutable prediction issued before kickoff, external receipt and independently verified clock",
        "evidence": "Timestamped raw prediction, fixture ID, kickoff UTC, issuer receipt, capture chain",
    },
    "independent_tsa_operator_identity": {
        "required": "Independent trust anchor and verified RFC3161 TSA operator identity",
        "evidence": "Third-party TSA policy, independently pinned CA fingerprint and RFC3161 token",
    },
    "verified_source_issuer_identity": {
        "required": "Externally verified data provider identity and authenticated ingestion",
        "evidence": "Provider contract/API identity, signing key provenance, immutable raw data",
    },
    "real_heldout_calibration": {
        "required": "Leakage-free real-event out-of-sample Brier, log loss and calibration vs baseline",
        "evidence": "Frozen model version, heldout fixture IDs, timestamps, settlement and reproducible report",
    },
    "real_heldout_positive_ev": {
        "required": "Real contemporaneous odds, costs and robust uncertainty intervals, not hypothetical edge",
        "evidence": "Bookmaker odds snapshot before kickoff, market liquidity, closing odds, settlement and uncertainty",
    },
    "deployment_risk_controls": {
        "required": "Audited kill switch, monitoring, limits, rollback and production sign-off",
        "evidence": "Live deployment checklist, monitoring tests, manual approval and rollback drill",
    },
}


def evidence_inventory(evidence=None):
    evidence = evidence if isinstance(evidence, dict) else {}
    items = []
    for name, requirement in CHECKS.items():
        item = evidence.get(name)
        items.append({
            "id": name,
            "requirement": requirement["required"],
            "expected_evidence": requirement["evidence"],
            "status": "NEEDS_INDEPENDENT_AUDIT" if isinstance(item, dict)
                      and item.get("artifact_reference") else "MISSING",
        })
    return {
        "schema_version": 1,
        "status": "HOLD",
        "checks": items,
        "production_recommendations": "DISABLED",
        "verified_completion_percentage": None,
        "note": "Artifact references and assertions alone never prove authenticity.",
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-json", type=Path)
    args = parser.parse_args()
    data = None
    if args.evidence_json:
        try:
            if args.evidence_json.stat().st_size > 100_000:
                raise ValueError("oversized")
            data = json.loads(args.evidence_json.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            data = None
    print(json.dumps(evidence_inventory(data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
