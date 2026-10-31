"""Sportmonks V3 free-league fixtures, reduced to non-betting research metadata.

Only Danish Superliga (271) and Scottish Premiership (501), subject to the
owner's existing optional SPORTMONKS_API_TOKEN and actual free entitlement.
No live odds, unverified final scores, secret values, or model inputs.
"""
from datetime import date, datetime, timezone

FREE_LEAGUES = {271: "denmark_superliga", 501: "scottish_premiership"}
MAX_PAGE_ROWS = 80
MAX_PUBLIC_ROWS = 12


def extract_free_fixtures(payload, *, expected_day):
    """Return (sanitised fixtures, partial page) without assuming completeness.

    Sportmonks V3 participants use meta.location, not list order.
    starting_at_timestamp is an actual UNIX instant; reject naive date strings.
    """
    if isinstance(expected_day, str):
        expected_day = date.fromisoformat(expected_day)
    if not isinstance(expected_day, date) or isinstance(expected_day, datetime):
        raise ValueError("INVALID_SPORTMONKS_DAY")
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("INVALID_SPORTMONKS_FIXTURES")
    if payload.get("errors") or payload.get("error"):
        raise ValueError("SPORTMONKS_PROVIDER_ERROR")
    data = payload["data"]
    if len(data) > MAX_PAGE_ROWS:
        # Safe cap: do not accept a vendor response that exceeds the
        # bounded sample and creates unaccounted commercial payloads.
        raise ValueError("SPORTMONKS_RESPONSE_TOO_MANY_ROWS")
    pagination = payload.get("pagination")
    if pagination is not None and not isinstance(pagination, dict):
        raise ValueError("INVALID_SPORTMONKS_PAGINATION")
    more = bool(isinstance(pagination, dict) and pagination.get("has_more") is True)
    if isinstance(pagination, dict) and pagination.get("current_page") not in (None, 1):
        raise ValueError("UNEXPECTED_SPORTMONKS_PAGE")
    rows, seen = [], set()
    for item in data:
        if not isinstance(item, dict):
            continue
        league_id = item.get("league_id")
        if type(league_id) is not int or league_id not in FREE_LEAGUES:
            continue
        event_id, started = item.get("id"), item.get("starting_at_timestamp")
        if (type(event_id) is not int or event_id <= 0
                or type(started) is not int or not 946684800 <= started <= 4102444800):
            continue
        try:
            kickoff = datetime.fromtimestamp(started, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            continue
        if kickoff.date() != expected_day:
            # Do not let ignored date filters create false current-day coverage.
            continue
        participants = item.get("participants")
        if not isinstance(participants, list) or not 2 <= len(participants) <= 12:
            continue
        sides = {}
        for player in participants:
            if not isinstance(player, dict):
                continue
            meta = player.get("meta")
            side = meta.get("location") if isinstance(meta, dict) else None
            identity = player.get("id")
            name = player.get("name")
            if (side not in ("home", "away") or side in sides
                    or type(identity) is not int or identity <= 0
                    or not isinstance(name, str) or not name.strip()
                    or len(name) > 100):
                sides = {}
                break
            sides[side] = (identity, name.strip())
        if set(sides) != {"home", "away"} or sides["home"][0] == sides["away"][0]:
            continue
        if sides["home"][1] == sides["away"][1]:
            continue
        ident = (league_id, event_id)
        if ident in seen:
            continue
        seen.add(ident)
        rows.append({
            "league": FREE_LEAGUES[league_id],
            "provider_event_id": str(event_id),
            "home": sides["home"][1],
            "away": sides["away"][1],
            "kickoff_utc": kickoff.isoformat(),
            "status": "SCHEDULED" if item.get("state_id") == 1 else "UNKNOWN",
        })
        if len(rows) == MAX_PUBLIC_ROWS:
            more = more or len(data) > MAX_PUBLIC_ROWS
            break
    return rows, more
