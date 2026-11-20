"""Offline J3 home/away venue split audit for historical *claims*.

No source credentials, internet calls, model promotion, betting quotes or
forecast training. This function never authenticates input source records:
timestamps and a provider-supplied event ID are only syntactic claims.

The only purpose is to prevent overall form being presented as away strength
and to reject post-forecast history (including LIVE/HT masquerading as FT).
"""
from datetime import datetime, timedelta, timezone
import re

SCHEMA = "football-king-j3-venue-split-shadow-v1"
PRODUCTION_RECOMMENDATIONS = "DISABLED"
MAX_HISTORY = 1200
MIN_PREMATCH_BUFFER = timedelta(minutes=10)
SEASON_START = datetime(2026, 8, 1, tzinfo=timezone.utc)
SEASON_END = datetime(2027, 8, 1, tzinfo=timezone.utc)
# Professional J3 matches are indexed by Japan-local calendar matchday,
# not by exact provider-supplied UTC kickoff (which can differ across feeds).
JAPAN_TIME = timezone(timedelta(hours=9))
ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9:_-]{1,79}\Z")


def _id(value):
    return type(value) is str and ID_PATTERN.fullmatch(value) is not None


def _time(value):
    if type(value) is not str or len(value) > 50:
        raise ValueError("INVALID_ASOF_OR_MATCH_TIME")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_ASOF_OR_MATCH_TIME") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NAIVE_MATCH_TIME")
    return dt.astimezone(timezone.utc)


def _identity(row):
    if (not isinstance(row, dict) or row.get("league") != "j3"
            or row.get("season") != "2026-27"
            or any(not _id(row.get(key)) for key in ("event_id", "home_id", "away_id"))
            or row["home_id"] == row["away_id"]):
        raise ValueError("INVALID_J3_FIXTURE_IDENTITY")


def _fraction(count, total):
    return round(count / total, 6) if total else None


def _summary(wins, draws, losses):
    total = wins + draws + losses
    return {
        "matches": total, "wins": wins, "draws": draws, "losses": losses,
        "win_fraction_unverified": _fraction(wins, total),
        "draw_fraction_unverified": _fraction(draws, total),
        "loss_fraction_unverified": _fraction(losses, total),
        "venue_only_history_metadata": True,
        "source_result_independently_authenticated": False,
    }


def audit(target, history, *, as_of_utc):
    """Review only older claimed FT results, never create a bet or model edge.

    Any malformed, duplicated, post-cutoff or wrong-season entry rejects the
    entire supplied cohort. Nothing is silently excluded and no repair uses
    results from the current target fixture.
    """
    _identity(target)
    cutoff = _time(as_of_utc)
    target_ko = _time(target.get("kickoff_utc"))
    if (not SEASON_START <= target_ko < SEASON_END
            or cutoff < SEASON_START
            or not cutoff + MIN_PREMATCH_BUFFER <= target_ko):
        raise ValueError("TARGET_NOT_VALID_PREMATCH")
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise ValueError("INVALID_J3_HISTORY_SIZE")

    home_w = home_d = home_l = 0
    away_w = away_d = away_l = 0
    seen_ids, seen_fixtures, seen_team_matchdays = set(), set(), set()
    for row in history:
        _identity(row)
        event_id = row["event_id"]
        if event_id == target["event_id"] or event_id in seen_ids:
            raise ValueError("DUPLICATE_OR_TARGET_EVENT_ID")
        kickoff = _time(row.get("kickoff_utc"))
        fixture_key = (row["home_id"], row["away_id"], kickoff)
        if fixture_key in seen_fixtures:
            raise ValueError("DUPLICATE_HISTORICAL_FIXTURE")
        # Some publishers assign different IDs or drift kickoff timestamps.
        # A club cannot legitimately play two distinct J3 league games on
        # one JST matchday: reject the entire ambiguous input set, not just
        # drop whichever row would be less favorable to the away record.
        local_matchday = kickoff.astimezone(JAPAN_TIME).date()
        team_days = ((row["home_id"], local_matchday),
                     (row["away_id"], local_matchday))
        if any(entry in seen_team_matchdays for entry in team_days):
            raise ValueError("AMBIGUOUS_LOCAL_MATCHDAY_TEAM")
        seen_ids.add(event_id)
        seen_fixtures.add(fixture_key)
        seen_team_matchdays.update(team_days)

        if row.get("match_status") != "FT":
            raise ValueError("HISTORY_NOT_FINAL")
        h, a = row.get("home_goals"), row.get("away_goals")
        if (type(h) is not int or type(a) is not int
                or not 0 <= h <= 30 or not 0 <= a <= 30):
            raise ValueError("INVALID_REGULATION_SCORE")
        observed = _time(row.get("final_observed_utc"))
        archived = _time(row.get("archived_utc"))
        if (not SEASON_START <= kickoff < SEASON_END
                or not kickoff < observed <= kickoff + timedelta(hours=6)
                or not observed <= archived <= cutoff
                or kickoff >= target_ko):
            raise ValueError("POST_CUTOFF_OR_UNSAFE_FT_HISTORY")

        if row["home_id"] == target["home_id"]:
            home_w += h > a
            home_d += h == a
            home_l += h < a
        if row["away_id"] == target["away_id"]:
            away_w += a > h
            away_d += a == h
            away_l += a < h

    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": "UNAUTHENTICATED_J3_HISTORY_AND_NO_CALIBRATED_DRAW_MODEL",
        "league": "j3", "season": "2026-27",
        "target_event_id": target["event_id"],
        "target_kickoff_utc": target_ko.isoformat(),
        "as_of_utc": cutoff.isoformat(),
        "history_rows_inspected": len(history),
        "target_home_at_home": _summary(home_w, home_d, home_l),
        "target_away_away": _summary(away_w, away_d, away_l),
        "as_of_metadata_only_not_authenticated": True,
        "independently_certified_history_cases": 0,
        "venue_form_independently_verified": False,
        "actual_target_ft_verified": False,
        "j3_market_or_model_coverage_verified": False,
        "calibrated_draw_probability_available": False,
        "positive_ev_verified": False,
        "bookmaker_odds": None,
        "recommended_stake": None,
        "bet_eligible": False,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
