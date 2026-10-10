"""Fail-closed routing of already-audited free fixture sources.

This is schedule-only failover, never a substitute for executable odds.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def route(primary, wide, *, now=None):
    now = now or datetime.now(timezone.utc)
    providers = primary.get("providers", []) if isinstance(primary, dict) and isinstance(primary.get("providers"), list) else []
    active = [p["provider"] for p in providers if isinstance(p, dict)
              and p.get("status") in ("FETCHED", "AVAILABLE", "OK")
              and p.get("sampled_fixture_count", 0) > 0]
    backup = wide.get("backup_scheduled_fixtures", []) if isinstance(wide, dict) else []
    valid_backup = (isinstance(wide, dict)
                    and wide.get("status") == "RESEARCH_ONLY"
                    and wide.get("production_recommendations") == "DISABLED"
                    and isinstance(backup, list))
    schedule_backup = [p for p in backup if isinstance(p, dict)
                       and p.get("backup_for_schedule_only") is True
                       and p.get("market_confirmed") is False
                       and p.get("production_recommendations") == "DISABLED"] if valid_backup else []
    # Reject expired or future-dated published source snapshots. A cached
    # successful response is not proof that the API is currently available.
    def fresh(payload, field, max_hours=36):
        if not isinstance(payload, dict):
            return False
        try:
            stamp = datetime.fromisoformat(payload[field].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                return False
            age = (now - stamp.astimezone(timezone.utc)).total_seconds()
            return -300 <= age <= max_hours * 3600
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            return False

    primary_fresh = fresh(primary, "generated_utc")
    backup_fresh = fresh(wide, "generated_utc")
    if not backup_fresh:
        schedule_backup = []
    primary_valid = (primary_fresh and isinstance(primary, dict)
                     and primary.get("status") == "RESEARCH_ONLY")
    if primary_valid and active:
        state, source = "PRIMARY_SCHEDULE_ONLY", "secondary_free_sources"
    elif schedule_backup:
        state, source = "BACKUP_SCHEDULE_ONLY", "openligadb"
    else:
        state, source = "NO_VERIFIED_SCHEDULE_SOURCE", None
    return {
        "schema": "football-king-free-source-failover-v1",
        "as_of_utc": now.isoformat(),
        "status": state,
        "selected_source": source,
        "available_primary_providers": active if primary_valid else [],
        "backup_fixture_count": len(schedule_backup),
        "schedule_only": True,
        "executable_odds_fallback_available": False,
        "can_generate_model_predictions": False,
        "production_recommendations": "DISABLED",
    }


def publish(site):
    site = Path(site)
    def read(name):
        try:
            return json.loads((site / name).read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            return None
    output = route(read("extra_sources.json"), read("wide_leagues.json"))
    (site / "free_source_failover.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="app/site")
    publish(Path(parser.parse_args().site))
