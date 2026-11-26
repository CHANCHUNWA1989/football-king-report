"""Fail-closed production recommendation readiness audit. No fabricated evidence."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = ("live_api_verified", "prematch_quote_fresh", "independent_model_validated",
            "time_split_backtest_passed", "forward_settled_sample_passed",
            "lineup_verified", "settlement_tracking_verified")

EXPECTED_GATE_KEYS = (
    "utc_fixture_identity", "source_time_quota_licence", "paired_asian_totals",
    "bookmaker_cross_feed_dedupe", "sealed_point_in_time",
    "out_of_sample_calibration", "model_promotion_safety",
)


def quality_gate_states(quality):
    """Descriptive states only: missing, invalid or repeated keys remain HOLD."""
    rows = quality.get("checks") if isinstance(quality, dict) else None
    rows = rows if isinstance(rows, list) else []
    result = {}
    for key in EXPECTED_GATE_KEYS:
        matches = [row for row in rows if isinstance(row, dict) and row.get("key") == key]
        state = matches[0].get("state") if len(matches) == 1 else None
        result[key] = state if isinstance(state, str) and state in ("PASS", "PARTIAL", "HOLD") else "HOLD"
    return result

def audit(evidence, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(evidence, dict):
        evidence = {}
    checks = {}
    for key in REQUIRED:
        item = evidence.get(key)
        # A self-attested boolean is not verifiable proof.
        ok = (isinstance(item, dict) and item.get("passed") is True
              and isinstance(item.get("artifact_sha256"), str)
              and len(item["artifact_sha256"]) == 64
              and all(c in "0123456789abcdef" for c in item["artifact_sha256"])
              and item.get("reviewed_by") not in (None, "", "self"))
        # Metadata cannot establish authenticity; never mark as passed here.
        checks[key] = {"passed": False, "metadata_present": bool(ok),
                       "reason": "AUTHENTICATED_EVIDENCE_REVIEW_REQUIRED"}
    # Hash and reviewer metadata alone cannot establish actual independent validation.
    # No promotion until an authenticated verification service is implemented.
    return {"schema": "football-king-readiness-v1", "generated_utc": now.isoformat(),
            "status": "HOLD", "production_recommendations": "DISABLED",
            "reason": "TRUSTED_EVIDENCE_VERIFIER_NOT_IMPLEMENTED",
            "checks": checks, "missing_or_unverified": [k for k,v in checks.items() if not v["passed"]]}


def _read_json(path):
    try:
        p = Path(path)
        if p.stat().st_size > 2_000_000:
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def grounded_progress(settled, gates, private, market):
    """Read actual archived evidence, not self-declared certificate Booleans."""
    from collections import Counter
    samples = settled.get("samples") if isinstance(settled, dict) else None
    complete = isinstance(samples, list) and len(samples) <= 20000
    seen = {}
    conflicts = set()
    invalid = 0

    def utc(value):
        if not isinstance(value, str):
            raise ValueError("INVALID_TIME")
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None:
            raise ValueError("NAIVE_TIME")
        return d.astimezone(timezone.utc)

    # Reject over-limit archives rather than reporting a selected prefix.
    for s in samples if complete else []:
        try:
            if not isinstance(s, dict) or not isinstance(s.get("key"), str):
                raise ValueError("INVALID_ROW")
            if len(s["key"]) > 2048:
                raise ValueError("INVALID_KEY_LENGTH")
            parts = json.loads(s["key"])
            if (not isinstance(parts, list) or len(parts) != 4
                    or not all(isinstance(x, str) and x and x == x.strip() for x in parts)
                    or parts[1] == parts[2] or s.get("league") != parts[0]):
                raise ValueError("INVALID_IDENTITY")
            kickoff = utc(s["kickoff_utc"])
            if utc(parts[3]) != kickoff:
                raise ValueError("INCONSISTENT_KICKOFF")
            key = (*parts[:3], kickoff.isoformat())
            normalized = dict(s, key=key, kickoff_utc=kickoff.isoformat())
            for field in ("forecast_utc", "market_utc"):
                if field in normalized:
                    normalized[field] = utc(normalized[field]).isoformat()
            if key in seen and seen[key][0] != normalized:
                conflicts.add(key)
            elif key not in seen:
                seen[key] = (normalized, kickoff)
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            invalid += 1
    valid = [pair for key, pair in seen.items() if key not in conflicts]
    weeks = {(d.isocalendar().year, d.isocalendar().week) for _, d in valid}
    league_counts = Counter(s.get("league") for s, _ in valid)
    independently_marked = sum(
        s.get("fixture_result_source_independently_verified") is True
        for s, _ in valid)
    passed_gates = sum(state == "PASS" for state in quality_gate_states(gates).values())
    collector_status = private.get("collector_status", "NOT_RUN")
    return {
        "settled_cases_in_archive": len(valid),
        "archive_identity_scan_complete": complete,
        "invalid_fixture_rows": invalid,
        "conflicting_fixture_keys": len(conflicts),
        "research_utc_week_blocks": len(weeks),
        "certified_week_blocks": 0,
        "settled_cases_required": 300,
        "additional_settled_cases_needed": max(0, 300 - len(valid)),
        # Row flags are unverified source claims. No admitted evidence route exists.
        "result_rows_marked_independently_verified": independently_marked,
        "independently_verified_result_cases": 0,
        "independent_week_blocks": len(weeks),
        "minimum_week_blocks": 12,
        "leagues_with_40_settlements": sum(n >= 40 for n in league_counts.values()),
        "minimum_leagues_with_40": 4,
        "seven_quality_gates_passed": passed_gates,
        "seven_quality_gates_required": 7,
        "private_collector_status": collector_status,
        "private_quotes_collected": len(private.get("quotes", []))
        if isinstance(private.get("quotes"), list) else 0,
        "derived_market_consensus_events": market.get("event_count", 0)
        if market.get("status") == "RESEARCH_ONLY" else 0,
        "market_consensus_is_executable_quote": False,
        "authenticated_calibration_and_manual_approval": False,
        "production_recommendations": "DISABLED",
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", default="sources/recommendation_evidence.json")
    parser.add_argument("--output", default="output/recommendation_readiness.json")
    parser.add_argument("--settled", default="evidence/settled.json")
    parser.add_argument("--quality", default="sources/seven_quality_gates_latest.json")
    parser.add_argument("--private", default="output/private_all_market_quotes.json")
    parser.add_argument("--market", default="market/latest.json")
    args = parser.parse_args()
    path = Path(args.evidence)
    try:
        evidence = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        evidence = {}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    report = audit(evidence)
    report["grounded_progress"] = grounded_progress(
        _read_json(args.settled), _read_json(args.quality),
        _read_json(args.private), _read_json(args.market))
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PRODUCTION:", report["production_recommendations"], "REASON:", report["reason"])

if __name__ == "__main__":
    main()
