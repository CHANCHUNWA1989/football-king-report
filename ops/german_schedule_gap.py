"""Read-only schedule-gap diagnostic; never collect, publish or fill stale values."""
from datetime import datetime, timezone


def stamp(s):
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None or t.utcoffset().total_seconds() != 0:
        raise ValueError("NON_UTC_CLOCK")
    return t


def diagnose(snapshot, latest_run, now):
    if (snapshot.get("schema") != "football-king-openligadb-hourly-v1"
            or snapshot.get("production_recommendations") != "DISABLED"
            or latest_run.get("path") != ".github/workflows/football-king-german-live.yml"
            or latest_run.get("head_branch") != "main"):
        raise ValueError("UNTRUSTED_GERMAN_DIAGNOSTIC_INPUT")
    collected, created = stamp(snapshot["collected_utc"]), stamp(latest_run["created_at"])
    if now.tzinfo is None or max(collected, created) > now:
        raise ValueError("FUTURE_OR_NAIVE_CLOCK")
    age = (now - collected).total_seconds()
    gap = (now - created).total_seconds()
    reason = "WITHIN_RESEARCH_AGE"
    if age > 3 * 3600:
        if latest_run.get("status") != "completed":
            reason = "HOLD_LATEST_RUN_NOT_COMPLETED"
        elif latest_run.get("conclusion") != "success":
            reason = "HOLD_LATEST_RUN_FAILED"
        elif gap > 3 * 3600:
            reason = "HOLD_NO_RECENT_RUN_IN_OBSERVED_INVENTORY"
        else:
            reason = "HOLD_RECENT_RUN_BUT_STALE_PUBLISHED_POINTER"
    return dict(status=reason, snapshot_age_seconds=round(age), observed_run_age_seconds=round(gap),
                latest_observed_run_id=latest_run["id"], provider_failure_proven=False,
                schedule_root_cause_proven=False, fallback_allowed=False,
                production_recommendations="DISABLED")
