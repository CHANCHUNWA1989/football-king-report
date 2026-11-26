"""Provider-neutral prematch 1X2 ingest boundary.

Accepts independently supplied provider payloads, never asserts authenticity.
No network calls or provider credentials are embedded here.
"""
import math
from datetime import datetime, timedelta, timezone
from prematch_market import evaluate_prematch_market

OUTCOMES = ("home", "draw", "away")


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _identifier(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 128


def _hold(reason):
    return {"status": "HOLD", "reason": reason,
            "production_recommendations": "DISABLED"}


def normalize_provider_snapshot(payload, fixture, *, evaluated_at_utc,
                                model_version, model_probabilities,
                                max_kickoff_delta_seconds=60):
    """Map one provider quote to a trusted fixture registry entry, fail closed.

    Fixture must originate from an independently maintained fixture registry.
    Provider claims are not treated as proof of independent provenance.
    """
    if (not isinstance(payload, dict) or not isinstance(fixture, dict)
            or type(max_kickoff_delta_seconds) is not int
            or not 0 <= max_kickoff_delta_seconds <= 300):
        return _hold("INVALID_PROVIDER_PAYLOAD")
    for obj, keys in ((payload, ("provider_id", "provider_fixture_id",
                                "home_team_id", "away_team_id")),
                      (fixture, ("fixture_id", "home_team_id", "away_team_id"))):
        if any(not _identifier(obj.get(key)) for key in keys):
            return _hold("MISSING_PROVIDER_OR_FIXTURE_ID")
    if (payload["home_team_id"].strip() != fixture["home_team_id"].strip()
            or payload["away_team_id"].strip() != fixture["away_team_id"].strip()):
        return _hold("FIXTURE_TEAM_MISMATCH")
    provider_kickoff = _utc(payload.get("kickoff_at_utc"))
    fixture_kickoff = _utc(fixture.get("kickoff_at_utc"))
    captured = _utc(payload.get("captured_at_utc"))
    evaluated = _utc(evaluated_at_utc)
    if any(t is None for t in (provider_kickoff, fixture_kickoff, captured, evaluated)):
        return _hold("INVALID_PROVIDER_TIMESTAMP")
    if abs((provider_kickoff - fixture_kickoff).total_seconds()) > max_kickoff_delta_seconds:
        return _hold("FIXTURE_KICKOFF_MISMATCH")
    if not captured <= evaluated < fixture_kickoff:
        return _hold("POST_KICKOFF_OR_FUTURE_CAPTURE")
    odds = payload.get("decimal_odds")
    if not isinstance(odds, dict) or set(odds) != set(OUTCOMES):
        return _hold("INVALID_PROVIDER_ODDS")
    if not _identifier(model_version):
        return _hold("INVALID_MODEL_VERSION")
    snapshot = {
        "fixture_id": fixture["fixture_id"].strip(),
        "provider_id": payload["provider_id"].strip(),
        "model_version": model_version.strip(),
        "captured_at_utc": captured.isoformat(),
        "evaluated_at_utc": evaluated.isoformat(),
        "kickoff_at_utc": fixture_kickoff.isoformat(),
        "decimal_odds": odds, "model_probabilities": model_probabilities,
    }
    result = evaluate_prematch_market(snapshot)
    if result["status"] != "RESEARCH_ONLY":
        return result
    return {**result, "provider_fixture_id": payload["provider_fixture_id"].strip(),
            "provider_captured_at_utc": captured.isoformat(),
            "fixture_registry_id": fixture["fixture_id"].strip(),
            "provider_identity_verified": False,
            "fixture_registry_authenticity_verified": False,
            "capture_timestamp_attested": False,
            "production_recommendations": "DISABLED"}
