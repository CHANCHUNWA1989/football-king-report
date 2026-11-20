"""Phase 11 automated evidence-based GO/HOLD report.

No caller-supplied assertion may independently authorize live wagering.
"""
import hashlib
import json
import math
from prematch_release_gate import evaluate_release


def evaluate_ev_decision(market, *, transaction_cost=0.0, uncertainty=0.0,
                         min_net_ev=0.02, independently_validated=False):
    reasons = []
    if not isinstance(market, dict) or market.get("status") != "RESEARCH_ONLY":
        reasons.append("MARKET_NOT_VALIDATED")
    def number(value):
        return type(value) in (int, float) and math.isfinite(value)
    if not all(number(x) for x in (transaction_cost, uncertainty, min_net_ev)) or not (
            0 <= transaction_cost <= 1 and 0 <= uncertainty <= 1 and
            0 <= min_net_ev <= 1):
        reasons.append("INVALID_RISK_PARAMETERS")
    raw = market.get("expected_values", {}) if isinstance(market, dict) else {}
    if not isinstance(raw, dict) or set(raw) != {"home", "draw", "away"} or not all(
            number(x) for x in raw.values()):
        reasons.append("INVALID_EV_ESTIMATES")
    adjusted = {}
    if not reasons:
        adjusted = {key: round(value - transaction_cost - uncertainty, 8)
                    for key, value in raw.items()}
        if max(adjusted.values()) < min_net_ev:
            reasons.append("NET_EV_BELOW_THRESHOLD")
    if independently_validated is not True:
        reasons.append("INDEPENDENT_EV_VALIDATION_MISSING")
    # Even independent flag is an untrusted caller assertion.
    reasons.append("PRODUCTION_EV_AUTHORIZATION_UNAVAILABLE")
    return {"status": "HOLD", "net_ev_diagnostics": adjusted,
            "rejection_reasons": reasons,
            "production_recommendations": "DISABLED"}


def phase11_go_hold_report(*, commit_sha, ci_conclusions, market=None,
                           sandbox_evidence=None, tsa_evidence=None,
                           source_evidence=None, heldout_evidence=None,
                           transaction_cost=0.0, uncertainty=0.0):
    release = evaluate_release(
        commit_sha=commit_sha, ci_conclusions=ci_conclusions,
        sandbox_evidence=sandbox_evidence, tsa_evidence=tsa_evidence,
        source_evidence=source_evidence, heldout_evidence=heldout_evidence)
    ev = evaluate_ev_decision(market, transaction_cost=transaction_cost,
                              uncertainty=uncertainty)
    record = {"status": "HOLD", "release": release, "ev_gate": ev,
              "rejection_reasons": list(release["rejection_reasons"]) +
                                   list(ev["rejection_reasons"]),
              "production_recommendations": "DISABLED"}
    record["report_sha256"] = hashlib.sha256(json.dumps(
        record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return record
