"""Fail-closed pre-match evidence gate for offline research datasets.

Does not connect to providers or certify source authenticity, model calibration,
positive EV, or permission to recommend or place bets.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

REQUIRED = ("event_id", "competition", "kickoff_at", "captured_at",
            "bookmaker", "source_url", "market", "side", "line", "odds",
            "home_goals", "away_goals", "model_version", "forecast_created_at",
            "score_probabilities")
PRODUCTION_RECOMMENDATIONS = "DISABLED"
POSITIVE_EV_VERIFIED = False

def _dt(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid ISO timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timezone-aware timestamps required")
    return result.astimezone(timezone.utc)

def _number(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a number")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid decimal") from exc
    if not d.is_finite():
        raise ValueError("nonfinite decimal")
    return d

def validate_snapshot(record, *, max_quote_age_minutes=30):
    """Validate structure and chronology; returns immutable-style normalized copy.

    Caller must separately verify sources, scores, actual market availability,
    independently trained forecast provenance and absence of lookahead.
    """
    if not isinstance(record, dict):
        raise ValueError("snapshot must be mapping")
    missing = [key for key in REQUIRED if key not in record]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))
    for key in ("event_id", "competition", "bookmaker", "source_url", "model_version"):
        if not isinstance(record[key], str) or not record[key].strip():
            raise ValueError("missing text: " + key)
    if not record["source_url"].startswith("https://"):
        raise ValueError("HTTPS source URL required")
    kickoff = _dt(record["kickoff_at"])
    capture = _dt(record["captured_at"])
    forecast = _dt(record["forecast_created_at"])
    if not (forecast <= capture < kickoff):
        raise ValueError("forecast/quote must predate kickoff in chronological order")
    max_age = _number(max_quote_age_minutes)
    if max_age <= 0 or (kickoff-capture).total_seconds() > max_age * 60:
        raise ValueError("quote is stale at kickoff")
    market, side = record["market"], record["side"]
    if (market == "total" and side not in ("over", "under")) or (market == "handicap" and side not in ("home", "away")) or market not in ("total", "handicap"):
        raise ValueError("unsupported market/side")
    line = _number(record["line"])
    if line * 4 != (line * 4).to_integral_value():
        raise ValueError("line must be quarter-goal increment")
    odds = _number(record["odds"])
    if odds <= 1:
        raise ValueError("invalid decimal odds")
    for key in ("home_goals", "away_goals"):
        score = _number(record[key])
        if score < 0 or score != score.to_integral_value():
            raise ValueError("invalid score")
    probs = record["score_probabilities"]
    if not isinstance(probs, dict) or not probs:
        raise ValueError("score distribution required")
    total = Decimal(0)
    for key, value in probs.items():
        if not isinstance(key, str) or len(key.split("-")) != 2:
            raise ValueError("score keys must be 'home-away'")
        pair = key.split("-")
        if any(not x.isdecimal() for x in pair):
            raise ValueError("invalid score key")
        p = _number(value)
        if p < 0 or p > 1:
            raise ValueError("invalid score probability")
        total += p
    if abs(total-1) > Decimal("0.000001"):
        raise ValueError("score probabilities must sum to one")
    result = dict(record)
    result["evidence_status"] = "UNVERIFIED"
    result["positive_ev_verified"] = False
    result["production_recommendation_allowed"] = False
    return result

def validate_dataset(records, **kwargs):
    if not isinstance(records, (list, tuple)) or not records:
        raise ValueError("nonempty dataset required")
    normalized = [validate_snapshot(row, **kwargs) for row in records]
    # Decimal equality and UTC instants prevent aliases bypassing deduplication.
    identities = [(r["event_id"], r["market"], r["side"], _number(r["line"]), r["bookmaker"], _dt(r["captured_at"])) for r in normalized]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate market snapshot")
    return normalized
