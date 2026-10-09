"""Create public, point-in-time fixture observations; not a validated model backtest."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def utc(value):
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_UTC")
    return d.astimezone(timezone.utc)


def create_snapshot(report, status, run_id="local", attempt="1"):
    if report.get("checked_utc") != status.get("checked_utc"):
        raise ValueError("INCONSISTENT_AS_OF")
    checked = utc(report["checked_utc"])
    public_events = (report.get("fixtures") or {}).get("matches") or []
    observations = []
    for m in public_events[:1200]:
        if not isinstance(m, dict):
            continue
        kickoff = m.get("kickoff_utc")
        eligible = False
        if kickoff:
            try:
                eligible = ((utc(kickoff) - checked).total_seconds() > 600
                            and m.get("score_ft") is None
                            and m.get("status") == "SCHEDULED")
            except (TypeError, ValueError, OverflowError):
                pass
        observations.append({
            "league": m.get("league"), "event_id": m.get("event_id"),
            "date": m.get("date"), "kickoff_utc": kickoff,
            "home": m.get("home"), "away": m.get("away"),
            "source": m.get("source"), "source_url": m.get("source_url"),
            "source_captured_utc": m.get("captured_utc"),
            "eligible_for_prematch_evaluation": eligible,
            "exclusion_reason": None if eligible else ("UNKNOWN_KICKOFF_OR_POST_MATCH_OR_TOO_CLOSE"),
        })
    payload = {
        "schema": "football-king-public-asof-1",
        "as_of_utc": checked.isoformat(),
        "run_id": str(run_id), "run_attempt": str(attempt),
        "data_status": status.get("status"),
        "quality_status": status.get("quality_status"),
        "production_recommendations": "DISABLED",
        "independently_verified_results": False,
        "market_odds_available": False,
        "model_probabilities_available": False,
        "event_count": len(observations),
        "eligible_prematch_events": sum(bool(m["eligible_for_prematch_evaluation"]) for m in observations),
        "source_records": [{k: row.get(k) for k in
                            ("league", "source", "status", "captured_utc", "upstream_updated_utc",
                             "window_matches", "source_url")}
                           for row in report.get("fixture_source_records", [])[:20] if isinstance(row, dict)],
        "observations": observations,
    }
    packed = json.dumps(observations, sort_keys=True, ensure_ascii=False).encode("utf-8")
    payload["observations_sha256"] = hashlib.sha256(packed).hexdigest()
    return payload


def write(site, output, run_id="local", attempt="1"):
    site = Path(site)
    report = json.loads((site / "report.json").read_text(encoding="utf-8"))
    status = json.loads((site / "status.json").read_text(encoding="utf-8"))
    payload = create_snapshot(report, status, run_id=run_id, attempt=attempt)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    p.add_argument("--output", required=True)
    p.add_argument("--run-id", default="local")
    p.add_argument("--attempt", default="1")
    a = p.parse_args()
    result = write(a.site, a.output, a.run_id, a.attempt)
    print(json.dumps({"as_of_utc": result["as_of_utc"],
                      "event_count": result["event_count"],
                      "eligible_prematch_events": result["eligible_prematch_events"],
                      "model_probabilities_available": False}, ensure_ascii=False))
