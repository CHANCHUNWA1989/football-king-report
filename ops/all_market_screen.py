"""Market-neutral football research ranking. No fabricated model probabilities.

Accepts a JSON object with 'quotes' list and optional 'model_probabilities'.
Uncertified estimated EV is RESEARCH_ONLY, never VERIFIED_VALUE.
No automatic betting or untrusted self-certification.
"""
import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.private_h2h_evidence import FEED_SCHEMA, verify_bound_quotes
from ops.ev_sensitivity import analyze_scenarios, validate_settlement_probabilities

def evaluate(q, now):
    required = ("fixture_id", "market", "selection", "line", "decimal_odds", "source", "observed_utc", "kickoff_utc")
    missing = [k for k in required if q.get(k) is None or q.get(k) == ""]
    out = {k: q.get(k) for k in required}
    if "captured_utc" in q:
        out["captured_utc"] = q["captured_utc"]
    if missing:
        return {**out, "status": "INCOMPLETE", "reason": "MISSING_" + ",".join(missing)}
    try:
        odds = float(q["decimal_odds"])
        stamp = datetime.fromisoformat(q["observed_utc"].replace("Z", "+00:00"))
        kickoff = datetime.fromisoformat(q["kickoff_utc"].replace("Z", "+00:00"))
        if not math.isfinite(odds) or not 1.01 <= odds <= 100 or stamp.tzinfo is None or kickoff.tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError, AttributeError, OverflowError):
        return {**out, "status": "INVALID", "reason": "PRICE_OR_TIME_INVALID"}
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    age = (now - stamp.astimezone(timezone.utc)).total_seconds()
    if age < -60 or stamp >= kickoff or now >= kickoff:
        return {**out, "status": "INVALID", "reason": "NON_PREMATCH_OR_FUTURE_QUOTE"}
    out["quote_age_seconds"] = round(age)
    if age > 1200:
        return {**out, "status": "STALE", "reason": "QUOTE_OLDER_THAN_20_MINUTES"}
    probs = q.get("settlement_probabilities")
    # Fractional Asian lines need explicit full/half settlement probabilities.
    if "settlement_probabilities" not in q:
        return {**out, "status": "RESEARCH_ONLY", "reason": "NO_CALIBRATED_SETTLEMENT_DISTRIBUTION"}
    try:
        p = validate_settlement_probabilities(probs)
    except (ValueError, TypeError, OverflowError):
        return {**out, "status": "INVALID", "reason": "INVALID_SETTLEMENT_PROBABILITIES"}
    # Multiple supplied models describe sensitivity, not independent OOS
    # evidence. Invalid scenarios must not leave a misleading EV on screen.
    if "model_scenarios" in q:
        try:
            out.update(analyze_scenarios(q["model_scenarios"], odds, quote=q))
        except (ValueError, TypeError, OverflowError):
            return {**out, "status": "INVALID", "reason": "INVALID_MODEL_SCENARIOS"}
    else:
        out.update(ev_sensitivity_status="NOT_ASSESSED",
                   scenario_count=0, positive_ev_verified=False,
                   model_independence_verified=False,
                   sensitivity_is_confidence_interval=False)
    ev = p[0]*(odds-1) + p[1]*(odds-1)/2 - p[3]/2 - p[4]
    out["ev_per_unit"] = round(ev, 6)
    # Self-declared booleans in a quote are NOT independent certification evidence.
    # Fail closed until an audited, external validation gate is implemented.
    return {**out, "status": "RESEARCH_ONLY", "reason": "INDEPENDENT_CERTIFICATION_GATE_NOT_IMPLEMENTED"}

def screen(payload, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(payload, dict) or not isinstance(payload.get("quotes"), list):
        payload = {"quotes": []}
    bound = (payload.get("schema") == FEED_SCHEMA
             or payload.get("source") == "The Odds API private research"
             or any(isinstance(q, dict) and ("evidence" in q or "quote_id_kind" in q
                    or q.get("schema") == FEED_SCHEMA or q.get("provider") == "the_odds_api_v4")
                    for q in payload["quotes"][:100000]))
    check = {"status": "LEGACY_UNBOUND_RESEARCH", "accepted_quotes": 0,
             "complete_h2h_markets": 0, "independently_verified": False,
             "production_recommendations": "DISABLED", "rejected": {}}
    selected = payload["quotes"][:100000]
    if bound:
        if (payload.get("schema") != FEED_SCHEMA
                or payload.get("production_recommendations") != "DISABLED"
                or payload.get("requested_markets") != ["h2h"]):
            selected, rejected = [], {"INVALID_BOUND_FEED_CONTRACT": 1}
        else:
            selected, rejected = verify_bound_quotes(payload["quotes"], now=now)
        check.update(status="CONTENT_CHECKED_RESEARCH" if selected else "HOLD",
                     accepted_quotes=len(selected), complete_h2h_markets=len(selected)//3,
                     rejected=rejected)
    rows = [evaluate(q, now) for q in selected if isinstance(q, dict)]
    # A rechecked digest remains private and describes content consistency only.
    if bound:
        for item, quote in zip(rows, selected):
            item["evidence"] = quote["evidence"]
    rank = {"VERIFIED_VALUE": 0, "RESEARCH_ONLY": 1, "NO_VALUE": 2, "STALE": 3, "INCOMPLETE": 4, "INVALID": 5}
    # Sorting uncertified estimated EV descending would present an unproven
    # single-model edge as a ranked betting tip. Use stable identity order.
    rows.sort(key=lambda x: (rank.get(x["status"], 9),
                             str(x.get("fixture_id", "")),
                             str(x.get("market", "")),
                             str(x.get("selection", "")),
                             str(x.get("line", "")),
                             str(x.get("source", ""))))
    return {"schema": "football-king-all-market-screen-v1", "generated_utc": now.isoformat(),
            "status": ("HOLD" if bound and not rows else
                       "RESEARCH_ONLY" if not any(x["status"] == "VERIFIED_VALUE" for x in rows)
                       else "HAS_VERIFIED_VALUE"),
            "counts": {k: sum(x["status"] == k for x in rows) for k in rank}, "candidates": rows,
            "quote_evidence_validation": check}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(screen(data), f, ensure_ascii=False, indent=2)
