"""Offline The Odds API historical snapshot envelope parser (research only).

No HTTP calls, secrets, data downloads, model forecasts or recommendation enablement.
Documentation: https://the-odds-api.com/liveapi/guides/v4/
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

PRODUCTION_RECOMMENDATIONS = "DISABLED"
POSITIVE_EV_VERIFIED = False

def _time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO8601 string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid ISO8601 timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return dt.astimezone(timezone.utc)

def _price(value):
    if isinstance(value, bool):
        raise ValueError("invalid price")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid price") from exc
    if not result.is_finite() or result <= 1:
        raise ValueError("decimal odds must exceed one")
    return str(result)

def extract_historical_quotes(envelope):
    """Extract supported pre-kickoff quotes with provider snapshot provenance.

    Returned quotes are *not* compatible with validated model snapshots until
    independently archived pre-match forecasts and verified results are joined.
    """
    if not isinstance(envelope, dict) or not isinstance(envelope.get("data"), list):
        raise ValueError("invalid historical response envelope")
    timestamp = envelope.get("timestamp")
    captured = _time(timestamp)
    quotes = []
    for event in envelope["data"]:
        if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not event["id"]:
            raise ValueError("invalid event")
        kickoff = _time(event.get("commence_time"))
        if captured >= kickoff:
            continue
        for book in event.get("bookmakers", []):
            if not isinstance(book, dict) or not isinstance(book.get("key"), str) or not book["key"]:
                raise ValueError("invalid bookmaker")
            for market in book.get("markets", []):
                key = market.get("key")
                if key not in ("spreads", "totals"):
                    continue
                if key == "spreads":
                    home, away = event.get("home_team"), event.get("away_team")
                    if (not isinstance(home, str) or not home.strip()
                        or not isinstance(away, str) or not away.strip()
                        or home.strip() == away.strip()):
                        raise ValueError("handicap requires distinct home and away team names")
                for outcome in market.get("outcomes", []):
                    if not isinstance(outcome, dict):
                        raise ValueError("invalid outcome")
                    point = outcome.get("point")
                    if point is None:
                        raise ValueError("missing market line")
                    try:
                        line = Decimal(str(point))
                    except (InvalidOperation, ValueError) as exc:
                        raise ValueError("invalid line") from exc
                    if not line.is_finite() or line * 4 != (line * 4).to_integral_value():
                        raise ValueError("line must be finite quarter-goal increment")
                    selection = outcome.get("name")
                    if key == "totals" and selection not in ("Over", "Under"):
                        raise ValueError("unsupported total selection")
                    if key == "spreads" and selection not in (home, away):
                        raise ValueError("unsupported handicap selection")
                    quotes.append({
                        "event_id": event["id"],
                        "kickoff_at": event["commence_time"],
                        "captured_at": timestamp,
                        "bookmaker": book["key"],
                        "market": "total" if key == "totals" else "handicap",
                        "side": selection.lower() if key == "totals" else ("home" if selection == home else "away"),
                        "line": str(line),
                        "odds": _price(outcome.get("price")),
                        "source_type": "historical_api_snapshot",
                        "independently_verified": False,
                        "positive_ev_verified": False,
                        "production_recommendation_allowed": False,
                    })
    return quotes
