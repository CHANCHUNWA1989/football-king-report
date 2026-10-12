"""Independent result consensus gate. No network calls or fabricated verification."""
from datetime import datetime, timezone

def _utc(value):
    if not isinstance(value, str):
        raise ValueError("timestamp missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone missing")
    return parsed.astimezone(timezone.utc)

def verify_result(fixture_id, kickoff_utc, observations):
    """Return HOLD unless two distinct independent providers agree on a valid FT result."""
    out = {"fixture_id": fixture_id, "status": "HOLD", "result": None, "source_ids": [], "reason": ""}
    try:
        kickoff = _utc(kickoff_utc)
        if not fixture_id or not isinstance(observations, list):
            raise ValueError("invalid fixture")
        accepted = {}
        provider_groups = {}
        for obs in observations:
            if obs.get("fixture_id") != fixture_id or obs.get("status") != "FT":
                continue
            provider = obs.get("provider_id")
            group = obs.get("independent_group_id", provider)
            source_time = _utc(obs.get("published_utc"))
            home, away = obs.get("home_goals"), obs.get("away_goals")
            if not isinstance(provider, str) or not provider.strip() or not isinstance(group, str) or not group.strip() or source_time <= kickoff or type(home) is not int or type(away) is not int or min(home, away) < 0:
                continue
            if provider in accepted and accepted[provider] != (home, away):
                out["reason"] = "SOURCE_CONFLICT"
                return out
            accepted[provider] = (home, away)
            if group in provider_groups and provider_groups[group] != (home, away):
                out["reason"] = "SOURCE_CONFLICT"
                return out
            provider_groups[group] = (home, away)
        out["source_ids"] = sorted(accepted)
        if len(provider_groups) < 2:
            out["reason"] = "INSUFFICIENT_INDEPENDENT_SOURCES"
        elif len(set(accepted.values())) != 1:
            out["reason"] = "SOURCE_CONFLICT"
        else:
            out.update(status="VERIFIED", result=list(next(iter(accepted.values()))), reason="TWO_SOURCE_AGREEMENT")
    except (ValueError, TypeError, AttributeError):
        out["reason"] = "INVALID_INPUT"
    return out
