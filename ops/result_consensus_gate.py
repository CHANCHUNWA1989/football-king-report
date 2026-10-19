"""Compare caller-supplied FT claims without authenticating their truth.

Provider/group labels, source URLs and digests do not establish who fetched the
original bytes, fixed fixture identity, actual kickoff, regulation-time results
or publisher/upstream independence. This pure routine cannot return VERIFIED.
"""
from datetime import datetime, timedelta, timezone

REGULATION_PERIOD = "REGULATION_90_MINUTES"

def _utc(value):
    if not isinstance(value, str):
        raise ValueError("timestamp missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone missing")
    return parsed.astimezone(timezone.utc)

def verify_result(fixture_id, kickoff_utc, observations):
    """Legacy API: return only unverified agreement of distinct provider claims.

    The recorded kickoff is an input claim, not an authenticated actual kickoff.
    Missing period data may remain an observation; an explicitly incompatible
    period or kickoff cannot participate in the regulation-result comparison.
    """
    out = {"fixture_id": fixture_id, "status": "HOLD", "result": None,
           "source_ids": [], "claimed_group_ids": [], "reason": "",
           "result_verified": False, "independently_verified": False,
           "raw_provenance_rechecked": False,
           "source_identity_independently_authenticated": False,
           "source_independence_authenticated": False,
           "fixture_identity_authenticated": False,
           "actual_kickoff_authenticated": False,
           "completion_authenticated": False, "period_authenticated": False,
           "eligible_for_model_scoring": False,
           "eligible_for_betting_promotion": False,
           "production_recommendations": "DISABLED"}
    try:
        kickoff = _utc(kickoff_utc)
        if (not isinstance(fixture_id, str) or not fixture_id.strip()
                or not isinstance(observations, list)):
            raise ValueError("invalid fixture")
        accepted = {}
        provider_groups = {}
        provider_to_group = {}
        published = []
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            if obs.get("fixture_id") != fixture_id or obs.get("status") != "FT":
                continue
            provider = obs.get("provider_id")
            group = obs.get("independent_group_id")
            try:
                source_time = _utc(obs.get("published_utc"))
                if any(key in obs and obs[key] != REGULATION_PERIOD
                       for key in ("result_period", "score_period", "period")):
                    continue
                if any(obs.get(key) is not None and _utc(obs[key]) != kickoff
                       for key in ("kickoff_utc", "publisher_kickoff_utc")):
                    continue
            except (ValueError, TypeError, AttributeError):
                continue
            home, away = obs.get("home_goals"), obs.get("away_goals")
            if (not isinstance(provider, str) or not provider.strip()
                    or not isinstance(group, str) or not group.strip()
                    or source_time < kickoff + timedelta(minutes=90)
                    or type(home) is not int or type(away) is not int
                    or min(home, away) < 0 or max(home, away) > 30):
                continue
            if provider in accepted and accepted[provider] != (home, away):
                out["reason"] = "SOURCE_CONFLICT"
                return out
            if provider in provider_to_group and provider_to_group[provider] != group:
                out["reason"] = "SOURCE_PROVENANCE_CONFLICT"
                return out
            provider_to_group[provider] = group
            accepted[provider] = (home, away)
            published.append(source_time)
            if group in provider_groups and provider_groups[group] != (home, away):
                out["reason"] = "SOURCE_CONFLICT"
                return out
            provider_groups[group] = (home, away)
        out["source_ids"] = sorted(accepted)
        out["claimed_group_ids"] = sorted(provider_groups)
        if len(accepted) < 2:
            out["reason"] = "INSUFFICIENT_DISTINCT_PROVIDER_CLAIMS"
        elif len(set(accepted.values())) != 1:
            out["reason"] = "SOURCE_CONFLICT"
        else:
            out.update(status="AGREED_UNVERIFIED",
                       result=list(next(iter(accepted.values()))),
                       latest_observed_utc=max(published).isoformat(),
                       reason="PROVIDER_CLAIMS_AGREE_AUTHENTICATION_MISSING")
    except (ValueError, TypeError, AttributeError, OverflowError):
        out["reason"] = "INVALID_INPUT"
    return out
