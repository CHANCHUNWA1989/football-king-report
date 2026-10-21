"""Evidence inventory for the mobile research artifact; never estimates betting skill."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def utc(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def inventory(market, summary, gates, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    now = now.astimezone(timezone.utc)
    if not all(isinstance(doc, dict) for doc in (market, summary, gates)):
        raise ValueError("INVALID_SNAPSHOTS")
    counts = summary.get("evidence_progress") or {}
    checks = gates.get("checks") or []
    if not isinstance(counts, dict) or not isinstance(checks, list):
        raise ValueError("INVALID_EVIDENCE")
    archived = counts.get("settled_cases_in_archive", 0)
    # Legacy aggregates and new marked counts are source claims, never proof.
    legacy_marked = counts.get("independently_verified_result_cases", 0)
    marked = counts.get("result_rows_marked_independently_verified", legacy_marked)
    passed = gates.get("passed", 0)
    total = gates.get("total", 7)
    required = counts.get("settled_cases_required", 300)
    if not all(type(x) is int and x >= 0 for x in (archived, legacy_marked, marked, passed, total, required)):
        raise ValueError("INVALID_COUNTS")
    if passed > total or legacy_marked > archived or marked > archived:
        raise ValueError("INCONSISTENT_COUNTS")
    if required != 300:
        raise ValueError("UNSUPPORTED_SETTLEMENT_REQUIREMENT")
    independent = 0  # Authenticated admission is not implemented in this pipeline.
    market_at = utc(market.get("as_of_utc"))
    summary_at = utc(summary.get("captured_utc"))
    gates_at = utc(gates.get("captured_utc"))
    stamps = (market_at, summary_at, gates_at)
    fresh = all(t is not None and 0 <= (now - t).total_seconds() <= 86400 for t in stamps)
    league_rows = market.get("leagues") or []
    league_names = sorted({row.get("league") for row in league_rows
                           if isinstance(row, dict) and isinstance(row.get("league"), str)})
    return {
        "schema": "football-king-evidence-readiness-v1",
        "captured_utc": now.isoformat(),
        "status": "RESEARCH_ONLY" if fresh else "HOLD",
        "snapshots_fresh_24h": fresh,
        "market_leagues": league_names,
        "market_event_count": market.get("event_count") if type(market.get("event_count")) is int else None,
        "market_is_model_prediction": False,
        "settled_archive_candidates": archived,
        "required_independent_settlements": required,
        "result_rows_marked_independently_verified": marked,
        "independently_verified_settlements": independent,
        "remaining_independent_settlements": max(0, required - independent),
        "quality_gates_passed": passed,
        "quality_gates_total": total,
        "ready_for_production": False,
        "production_recommendations": "DISABLED",
        "blockers": [
            *([] if fresh else ["STALE_OR_INVALID_SNAPSHOTS"]),
            "INSUFFICIENT_INDEPENDENT_SETTLEMENTS",
            *([] if passed == total else ["QUALITY_GATES_INCOMPLETE"]),
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--market", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--gates", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    def load(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    report = inventory(load(args.market), load(args.summary), load(args.gates))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "independent": report["independently_verified_settlements"],
                      "remaining": report["remaining_independent_settlements"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
