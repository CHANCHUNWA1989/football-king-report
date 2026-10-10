"""Market-neutral football research ranking. No fabricated model probabilities.

Accepts a JSON object with 'quotes' list and optional 'model_probabilities'.
Uncertified estimated EV is RESEARCH_ONLY, never VERIFIED_VALUE.
No automatic betting or untrusted self-certification.
"""
import argparse
import json
import math
from datetime import datetime, timezone

def evaluate(q, now):
    required = ("fixture_id", "market", "selection", "line", "decimal_odds", "source", "observed_utc", "kickoff_utc")
    missing = [k for k in required if q.get(k) is None or q.get(k) == ""]
    out = {k: q.get(k) for k in required}
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
    keys = ("full_win", "half_win", "push", "half_loss", "full_loss")
    if not isinstance(probs, dict) or any(k not in probs for k in keys):
        return {**out, "status": "RESEARCH_ONLY", "reason": "NO_CALIBRATED_SETTLEMENT_DISTRIBUTION"}
    try:
        p = [float(probs[k]) for k in keys]
        if any(not math.isfinite(x) or x < 0 or x > 1 for x in p) or abs(sum(p)-1) > 1e-5:
            raise ValueError()
    except (ValueError, TypeError):
        return {**out, "status": "INVALID", "reason": "INVALID_SETTLEMENT_PROBABILITIES"}
    ev = p[0]*(odds-1) + p[1]*(odds-1)/2 - p[3]/2 - p[4]
    out["ev_per_unit"] = round(ev, 6)
    # Self-declared booleans in a quote are NOT independent certification evidence.
    # Fail closed until an audited, external validation gate is implemented.
    return {**out, "status": "RESEARCH_ONLY", "reason": "INDEPENDENT_CERTIFICATION_GATE_NOT_IMPLEMENTED"}

def screen(payload, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(payload, dict) or not isinstance(payload.get("quotes"), list):
        payload = {"quotes": []}
    rows = [evaluate(q, now) for q in payload["quotes"][:100000] if isinstance(q, dict)]
    rank = {"VERIFIED_VALUE": 0, "RESEARCH_ONLY": 1, "NO_VALUE": 2, "STALE": 3, "INCOMPLETE": 4, "INVALID": 5}
    rows.sort(key=lambda x: (rank.get(x["status"], 9), -x.get("ev_per_unit", -999)))
    return {"schema": "football-king-all-market-screen-v1", "generated_utc": now.isoformat(),
            "status": "RESEARCH_ONLY" if not any(x["status"] == "VERIFIED_VALUE" for x in rows) else "HAS_VERIFIED_VALUE",
            "counts": {k: sum(x["status"] == k for x in rows) for k in rank}, "candidates": rows}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(screen(data), f, ensure_ascii=False, indent=2)
