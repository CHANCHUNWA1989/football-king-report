"""Research-only manual HKJC 1X2 snapshot audit; no scraping or betting."""
import argparse
import json
import math
from datetime import datetime, timezone


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if dt.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return dt.astimezone(timezone.utc)


def validate(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("INVALID_SNAPSHOT")
    if snapshot.get("source") != "HKJC_MANUAL_SCREENSHOT":
        raise ValueError("UNVERIFIED_SOURCE")
    if snapshot.get("market") != "FT_1X2":
        raise ValueError("WRONG_MARKET")
    fixture = snapshot.get("fixture_id")
    if not isinstance(fixture, str) or not fixture.strip():
        raise ValueError("MISSING_FIXTURE")
    captured = parse_time(snapshot.get("captured_at_utc"))
    kickoff = parse_time(snapshot.get("kickoff_utc"))
    if captured >= kickoff:
        raise ValueError("NOT_PREMATCH")
    odds = snapshot.get("odds")
    if not isinstance(odds, dict) or set(odds) != {"home", "draw", "away"}:
        raise ValueError("INVALID_ODDS")
    vals = [odds[k] for k in ("home", "draw", "away")]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 1 for v in vals):
        raise ValueError("INVALID_ODDS")
    inv = [1 / v for v in vals]
    total = sum(inv)
    if not 1 <= total <= 1.5:
        raise ValueError("IMPLAUSIBLE_OVERROUND")
    return {
        "status": "RESEARCH_ONLY",
        "fixture_id": fixture,
        "market": "FT_1X2",
        "captured_at_utc": captured.isoformat(),
        "kickoff_utc": kickoff.isoformat(),
        "overround": round(total - 1, 6),
        "market_probabilities": {k: round(v / total, 6) for k, v in zip(("home", "draw", "away"), inv)},
        "source_independently_authenticated": False,
        "production_recommendations": "DISABLED",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as f:
        result = validate(json.load(f))
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
