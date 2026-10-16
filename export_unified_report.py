"""Export verified stored football market metadata as a research-only report.

Market consensus is NOT a forecast. This exporter never invents predictions.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path("market/latest.json")
TARGET = Path("integration/outbox/football.json")

def main():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    stamp = datetime.fromisoformat(data["as_of_utc"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    events = data.get("events", [])
    valid = (
        stamp.tzinfo is not None
        and 0 <= (now - stamp).total_seconds() <= 36 * 3600
        and data.get("status") == "RESEARCH_ONLY"
        and isinstance(events, list)
        and len(events) == data.get("event_count")
        and len({e["source_event_id"] for e in events}) == len(events)
        and all(
            all(isinstance(e.get(k), (int, float)) and 0 <= e[k] <= 1 for k in ("p_home", "p_draw", "p_away"))
            and abs(sum(e[k] for k in ("p_home", "p_draw", "p_away")) - 1) < 0.001
            and e.get("prediction_or_value_bet") is False
            for e in events
        )
    )
    report = {
        "system": "football",
        "generated_at_utc": now.isoformat(),
        "mode": "RESEARCH_ONLY",
        "production_actions": "DISABLED",
        "source_status": {"odds_h2h": "DEGRADED" if valid else "UNAVAILABLE"},
        "forecast_count": 0,
        "settled_count": 0,
        "evaluation_metrics": {},
        "failures": ["NO_VALIDATED_FORECASTS"] + ([] if valid else ["MARKET_SNAPSHOT_INVALID_OR_STALE"]),
        "version": "football-market-export-v1",
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source_valid": valid, "events": len(events), "report": str(TARGET)}))

if __name__ == "__main__":
    main()
