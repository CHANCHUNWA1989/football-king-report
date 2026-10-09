"""Merge historical forward-study results without overwriting concurrent new samples.

Never turn evidence into a recommendation or treat independent verification as
completed. A conflicting settlement for the same fixture fails closed.
"""
import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "football-king-forward-research-1"
MAX_SAMPLES = 20000


def aware(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return t.astimezone(timezone.utc)


def valid_probs(values):
    return (isinstance(values, list) and len(values) == 3 and
            all(type(n) in (float, int) and math.isfinite(n) and 0 <= n <= 1 for n in values)
            and abs(sum(values) - 1) < 0.002)


def validate(doc):
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ValueError("INVALID_EVIDENCE_SCHEMA")
    if (doc.get("production_recommendations") != "DISABLED"
            or doc.get("results_independently_verified") is not False
            or doc.get("profitability_verified") is not False):
        raise ValueError("INVALID_EVIDENCE_SAFETY")
    samples = doc.get("samples")
    if not isinstance(samples, list) or len(samples) > MAX_SAMPLES:
        raise ValueError("INVALID_EVIDENCE_COLLECTION")
    if doc.get("n") != len(samples):
        raise ValueError("INCORRECT_EVIDENCE_COUNT")
    aware(doc["checked_utc"])
    seen = set()
    for s in samples:
        if not isinstance(s, dict) or not isinstance(s.get("key"), str) or not s["key"]:
            raise ValueError("INVALID_EVIDENCE_KEY")
        if s["key"] in seen:
            raise ValueError("DUPLICATE_EVIDENCE_KEY")
        seen.add(s["key"])
        if (s.get("production_recommendations") != "DISABLED"
                or s.get("fixture_result_source_independently_verified") is not False
                or type(s.get("y")) is not int or s["y"] not in (0, 1, 2)
                or not valid_probs(s.get("p")) or not valid_probs(s.get("m"))):
            raise ValueError("UNSAFE_SETTLEMENT")
        if "ab" in s:
            if (not valid_probs(s.get("ab"))
                    or s.get("ab_model") != "probability-shrink-to-uniform-fixed-0.15-v1"):
                raise ValueError("INVALID_SEALED_AB_EXPERIMENT")
        forecast = aware(s["forecast_utc"])
        market = aware(s["market_utc"])
        kickoff = aware(s["kickoff_utc"])
        if not (market <= forecast <= kickoff - timedelta(minutes=10)):
            raise ValueError("FORECAST_TIME_LEAKAGE")
    return samples


def merge(current, incoming):
    new = validate(incoming)
    old = validate(current) if current is not None else []
    combined = {s["key"]: s for s in old}
    added = 0
    for sample in new:
        key = sample["key"]
        if key in combined:
            if combined[key] != sample:
                raise ValueError("CONFLICTING_RESULT_FOR_SAME_FIXTURE")
        else:
            combined[key] = sample
            added += 1
    if len(combined) > MAX_SAMPLES:
        raise ValueError("EVIDENCE_CAP_REACHED")
    check = max([aware(incoming["checked_utc"])] +
                ([aware(current["checked_utc"])] if current else []))
    return {
        "schema": SCHEMA, "checked_utc": check.isoformat(),
        "samples": list(combined.values()), "n": len(combined),
        "newly_settled": added,
        "results_independently_verified": False,
        "profitability_verified": False,
        "production_recommendations": "DISABLED",
        "note": "Settled observations from public fixtures remain independently unverified.",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--current", required=True)
    p.add_argument("--incoming", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    old = json.loads(Path(args.current).read_text(encoding="utf-8")) if Path(args.current).exists() else None
    incoming = json.loads(Path(args.incoming).read_text(encoding="utf-8"))
    merged = merge(old, incoming)
    Path(args.output).write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"merged_samples": merged["n"], "newly_settled": merged["newly_settled"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
