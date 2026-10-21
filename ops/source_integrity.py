"""Fail-closed cross-source fixture and odds integrity checks.

Research-only: this module never turns an unverified quote into a recommendation.
All timestamps must be provider-originated and timezone-aware.
"""
from datetime import datetime, timezone
from math import isfinite


def _time(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("MISSING_PROVIDER_TIME")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_PROVIDER_TIME")
    return parsed.astimezone(timezone.utc)


def audit_quotes(quotes, *, now_utc, max_age_seconds=1800, kickoff_tolerance_seconds=300):
    """Return a safe HOLD report, with reasons; never average conflicting odds.

    Required quote fields: source, event_id, home_id, away_id, kickoff_utc,
    quoted_at_utc, market, selection, decimal_odds.
    """
    report = {"status": "HOLD", "production_recommendations": "DISABLED",
              "reason": "NO_VERIFIED_QUOTES", "verified_count": 0, "rejected": []}
    try:
        now = _time(now_utc)
    except (TypeError, ValueError, OverflowError):
        report["reason"] = "INVALID_AUDIT_TIME"
        return report
    if not isinstance(quotes, list) or len(quotes) < 2:
        return report
    valid = []
    for index, row in enumerate(quotes):
        reason = None
        try:
            if not isinstance(row, dict):
                raise ValueError("INVALID_ROW")
            fields = ("source", "event_id", "home_id", "away_id", "market", "selection")
            if any(not isinstance(row.get(k), str) or not row[k].strip() for k in fields):
                raise ValueError("MISSING_IDENTITY")
            if row["home_id"] == row["away_id"]:
                raise ValueError("INVALID_TEAMS")
            kickoff, quoted = _time(row.get("kickoff_utc")), _time(row.get("quoted_at_utc"))
            if not 0 <= (now - quoted).total_seconds() <= max_age_seconds:
                raise ValueError("STALE_OR_FUTURE_QUOTE")
            if quoted >= kickoff or now >= kickoff:
                raise ValueError("NOT_PREMATCH")
            odds = row.get("decimal_odds")
            if type(odds) not in (int, float) or not isfinite(odds) or odds <= 1:
                raise ValueError("INVALID_ODDS")
            valid.append((row, kickoff))
        except (ValueError, TypeError, OverflowError) as exc:
            reason = str(exc) or "INVALID_ROW"
        if reason:
            report["rejected"].append({"index": index, "reason": reason})
    if len(valid) < 2:
        report["reason"] = "INSUFFICIENT_VALID_QUOTES"
        return report
    first, kickoff = valid[0]
    identity = tuple(first[k] for k in ("event_id", "home_id", "away_id", "market", "selection"))
    sources = set()
    for row, time in valid:
        current = tuple(row[k] for k in ("event_id", "home_id", "away_id", "market", "selection"))
        if current != identity or abs((time - kickoff).total_seconds()) > kickoff_tolerance_seconds:
            report["reason"] = "FIXTURE_OR_MARKET_CONFLICT"
            return report
        if row["source"] in sources:
            report["reason"] = "DUPLICATE_SOURCE"
            return report
        sources.add(row["source"])
    report["verified_count"] = len(valid)
    report["reason"] = "CROSS_SOURCE_IDENTITY_VALIDATED_NOT_EXECUTABLE"
    return report
