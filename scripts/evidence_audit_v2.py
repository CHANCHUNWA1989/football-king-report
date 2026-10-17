#!/usr/bin/env python3
"""Read-only audit for research settlements. No betting recommendations."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path

def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(dt.timezone.utc)

def metric(rows, field):
    vals = [r for r in rows if field in r]
    if not vals:
        return {"n": 0, "log_loss": None, "brier": None}
    return {
        "n": len(vals),
        "log_loss": sum(-math.log(max(r[field][r["y"]], 1e-15)) for r in vals) / len(vals),
        "brier": sum(sum((p - int(i == r["y"])) ** 2 for i, p in enumerate(r[field])) for r in vals) / len(vals),
    }

def audit(doc):
    errors, seen, accepted = [], set(), []
    for idx, row in enumerate(doc.get("samples", [])):
        key = row.get("key")
        try:
            if not key or key in seen:
                raise ValueError("missing or duplicate key")
            seen.add(key)
            kickoff = timestamp(row["kickoff_utc"])
            if timestamp(row["forecast_utc"]) >= kickoff or timestamp(row["market_utc"]) >= kickoff:
                raise ValueError("post-kickoff forecast/market")
            if row.get("production_recommendations") != "DISABLED":
                raise ValueError("production recommendation flag not DISABLED")
            if type(row.get("y")) is not int or row["y"] not in (0, 1, 2):
                raise ValueError("invalid outcome")
            for field in ("p", "m", "ab"):
                if field not in row:
                    if field != "ab":
                        raise ValueError("missing " + field)
                    continue
                p = row[field]
                if len(p) != 3 or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or v > 1 for v in p) or abs(sum(p)-1)>1e-4:
                    raise ValueError("invalid probability vector: " + field)
            accepted.append(row)
        except (KeyError, ValueError, TypeError) as exc:
            errors.append({"index": idx, "error": str(exc)})
    paired = [r for r in accepted if "ab" in r]
    verified = [r for r in accepted if r.get("fixture_result_source_independently_verified") is True]
    return {
        "schema": "evidence-audit-v2",
        "research_only": True,
        "production_recommendations": "DISABLED",
        "sample_count": len(accepted),
        "independently_verified_count": len(verified),
        "unverified_count": len(accepted)-len(verified),
        "descriptive_unverified": {"A": metric(accepted,"p"), "market": metric(accepted,"m"),
            "A_B_paired": metric(paired,"p"), "B": metric(paired,"ab"), "market_B_paired": metric(paired,"m")},
        "verified_only": {"A": metric(verified,"p"), "market": metric(verified,"m")},
        "errors": errors,
        "promotion_eligible": False,
        "manual_review_required": bool(errors) or len(verified)<300,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="evidence/settled.json")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    report = audit(json.loads(Path(args.input).read_text(encoding="utf-8")))
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output == "-":
        print(payload, end="")
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    if report["errors"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
