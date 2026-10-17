"""Research-only source freshness and provenance validation."""
from datetime import datetime, timezone, timedelta

def check_source(source, observed_at, now, max_age_seconds=300):
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source is required")
    if type(max_age_seconds) is not int or max_age_seconds < 1:
        raise ValueError("invalid max age")
    def parse(value):
        if not isinstance(value, str):
            raise ValueError("timestamp must be a string")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc)
    observed, current = parse(observed_at), parse(now)
    age = (current - observed).total_seconds()
    reasons = []
    if age < 0:
        reasons.append("FUTURE_SOURCE_TIMESTAMP")
    if age > max_age_seconds:
        reasons.append("STALE_SOURCE")
    return {"verified_freshness": not reasons, "source": source.strip(),
            "age_seconds": age, "reasons": reasons,
            "research_only": True, "live_execution_allowed": False}
