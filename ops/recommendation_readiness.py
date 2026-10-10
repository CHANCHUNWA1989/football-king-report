"""Fail-closed production recommendation readiness audit. No fabricated evidence."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = ("live_api_verified", "prematch_quote_fresh", "independent_model_validated",
            "time_split_backtest_passed", "forward_settled_sample_passed",
            "lineup_verified", "settlement_tracking_verified")

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
        checks[key] = {"passed": bool(ok), "reason": "EVIDENCE_REVIEW_REQUIRED" if not ok else "EVIDENCE_METADATA_PRESENT"}
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
    samples = settled.get("samples") if isinstance(settled.get("samples"), list) else []
    unique = set()
    valid = []
    for s in samples[:20000]:
        if not isinstance(s, dict):
            continue
        try:
            kickoff = datetime.fromisoformat(s["kickoff_utc"].replace("Z", "+00:00"))
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
        if kickoff.tzinfo is None or s.get("league") is None:
            continue
        unique_key = (s.get("league"), s.get("key"), kickoff.isoformat())
        if unique_key in unique:
            continue
        unique.add(unique_key)
        valid.append((s, kickoff))
    weeks = {(d.isocalendar().year, d.isocalendar().week) for _, d in valid}
    league_counts = Counter(s.get("league") for s, _ in valid)
    independently_verified = sum(
        s.get("fixture_result_source_independently_verified") is True
        for s, _ in valid)
    passed_gates = sum(
        x.get("state") == "PASS" for x in gates.get("checks", [])
        if isinstance(x, dict)) if isinstance(gates.get("checks"), list) else 0
    collector_status = private.get("collector_status", "NOT_RUN")
    return {
        "settled_cases_in_archive": len(valid),
        "settled_cases_required": 300,
        "additional_settled_cases_needed": max(0, 300 - len(valid)),
        "independently_verified_result_cases": independently_verified,
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
