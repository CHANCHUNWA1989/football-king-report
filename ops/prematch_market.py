"""Fail-closed research-only 1X2 prematch odds and EV validation."""
import math
from datetime import datetime, timedelta, timezone

OUTCOMES = ("home", "draw", "away")


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo else None


def _number(value, lower, upper):
    return type(value) in (int, float) and math.isfinite(value) and lower <= value <= upper


def evaluate_prematch_market(snapshot, *, max_age_minutes=15, min_ev=0.02):
    hold = {"status": "HOLD", "reason": "INVALID_PREMATCH_MARKET",
            "production_recommendations": "DISABLED"}
    if (not isinstance(snapshot, dict) or type(max_age_minutes) is not int
            or not 1 <= max_age_minutes <= 120 or not _number(min_ev, 0, 1)):
        return hold
    for key in ("fixture_id", "provider_id", "model_version"):
        if not isinstance(snapshot.get(key), str) or not snapshot[key].strip():
            return hold
    captured = _utc(snapshot.get("captured_at_utc"))
    evaluated = _utc(snapshot.get("evaluated_at_utc"))
    kickoff = _utc(snapshot.get("kickoff_at_utc"))
    if captured is None or evaluated is None or kickoff is None:
        return hold
    if not captured <= evaluated < kickoff:
        return {**hold, "reason": "POST_KICKOFF_OR_FUTURE_CAPTURE"}
    if evaluated - captured > timedelta(minutes=max_age_minutes):
        return {**hold, "reason": "STALE_ODDS"}
    odds = snapshot.get("decimal_odds")
    probs = snapshot.get("model_probabilities")
    if (not isinstance(odds, dict) or not isinstance(probs, dict)
            or set(odds) != set(OUTCOMES) or set(probs) != set(OUTCOMES)
            or any(not _number(odds[k], 1.000001, 1000) for k in OUTCOMES)
            or any(not _number(probs[k], 0, 1) for k in OUTCOMES)):
        return hold
    if abs(sum(probs.values()) - 1) > 1e-6:
        return {**hold, "reason": "INVALID_PROBABILITY_SUM"}
    implied = {k: 1 / odds[k] for k in OUTCOMES}
    overround = sum(implied.values())
    if not 1 <= overround <= 1.5:
        return {**hold, "reason": "INVALID_MARKET_OVERROUND"}
    fair = {k: round(implied[k] / overround, 8) for k in OUTCOMES}
    ev = {k: round(probs[k] * odds[k] - 1, 8) for k in OUTCOMES}
    return {"status": "RESEARCH_ONLY",
            "reason": "UNVERIFIED_PREMATCH_MARKET_DIAGNOSTIC",
            "fixture_id": snapshot["fixture_id"].strip(),
            "provider_id": snapshot["provider_id"].strip(),
            "model_version": snapshot["model_version"].strip(),
            "overround": round(overround, 8),
            "bookmaker_margin": round(overround - 1, 8),
            "no_vig_probabilities": fair, "expected_values": ev,
            "candidate_outcomes": [k for k in OUTCOMES if ev[k] >= min_ev],
            "source_authenticity_verified": False,
            "model_calibration_verified": False,
            "positive_ev_verified": False,
            "production_recommendations": "DISABLED"}
