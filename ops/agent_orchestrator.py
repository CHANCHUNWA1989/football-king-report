"""Read-only, fail-closed audit of real Football King source snapshots."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

REQUIRED = ("ops/research_recommender.py", "ops/forward_validation.py", "ops/release_guard.py")
SNAPSHOTS = (
    ("market/latest.json", "as_of_utc", 16),
    ("sources/latest.json", "collected_utc", 24),
)

def inspect_snapshot(root, path, timestamp_field, max_age_hours, now):
    item = {"path": path, "status": "HOLD", "reason": "MISSING"}
    try:
        raw = root.joinpath(path).read_bytes()
        if len(raw) > 2_000_000:
            item["reason"] = "OVERSIZED"
            return item
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("INVALID_OBJECT")
        if data.get("production_recommendations") not in (None, "DISABLED"):
            raise ValueError("UNSAFE_PRODUCTION_FLAG")
        value = data.get(timestamp_field)
        if not isinstance(value, str):
            raise ValueError("MISSING_TIMESTAMP")
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("NAIVE_TIMESTAMP")
        age = now - stamp.astimezone(timezone.utc)
        if age < -timedelta(minutes=5):
            raise ValueError("FUTURE_TIMESTAMP")
        if age > timedelta(hours=max_age_hours):
            raise ValueError("STALE")
        if data.get("status") not in ("RESEARCH_ONLY", "READY_RESEARCH"):
            raise ValueError("SOURCE_NOT_READY")
        # A fresh response is not necessarily a usable research dataset.
        if path == "market/latest.json":
            leagues = data.get("leagues")
            if not isinstance(leagues, list) or not leagues:
                raise ValueError("EMPTY_MARKET_COVERAGE")
            if not any(isinstance(row, dict) and type(row.get("events")) is int
                       and row["events"] > 0 and isinstance(row.get("league"), str)
                       and bool(row["league"].strip()) for row in leagues):
                raise ValueError("NO_MARKET_EVENTS")
        elif path == "sources/latest.json":
            providers = data.get("providers")
            if not isinstance(providers, list) or not any(
                isinstance(row, dict) and isinstance(row.get("provider"), str)
                and bool(row["provider"].strip()) for row in providers
            ):
                raise ValueError("EMPTY_SOURCE_COVERAGE")
        item.update(status="READY_RESEARCH", reason=None, timestamp_utc=stamp.astimezone(timezone.utc).isoformat())
    except FileNotFoundError:
        pass
    except (ValueError, TypeError, UnicodeError, OSError, json.JSONDecodeError) as exc:
        item["reason"] = str(exc)[:100]
    return item

def audit(root: Path, now=None):
    now = now or datetime.now(timezone.utc)
    missing = [p for p in REQUIRED if not (root / p).is_file()]
    sources = [inspect_snapshot(root, *s, now) for s in SNAPSHOTS]
    healthy = not missing and all(s["status"] == "READY_RESEARCH" for s in sources)
    diagnostics = ([{"component": p, "reason": "MISSING_COMPONENT"} for p in missing] +
                   [{"component": s["path"], "reason": s["reason"]}
                    for s in sources if s["status"] != "READY_RESEARCH"])
    return {
        "schema": "football-king-agent-audit-v2",
        "checked_at_utc": now.isoformat(),
        "mode": "SHADOW_READ_ONLY",
        "production_recommendations": "DISABLED",
        "automatic_bets": False,
        "status": "READY_FOR_MANUAL_REVIEW" if healthy else "HOLD",
        "missing_components": missing,
        "diagnostics": diagnostics,
        "next_action": "MANUAL_REVIEW_ONLY" if healthy else "REFRESH_OR_REPAIR_INPUTS",
        "sources": sources,
        "actions_performed": [],
        "note": "Snapshot freshness and status are necessary, not proof of full coverage, calibrated predictions, or valid betting prices.",
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    data = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data + "\n", encoding="utf-8")
    print(data)
    return 0 if result["status"] != "HOLD" else 2

if __name__ == "__main__":
    raise SystemExit(main())
