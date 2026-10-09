"""Bounded provisional German points coverage from OpenLigaDB season match results.

Used ONLY when /getbltable returns empty. Community-reported finished 90-minute
scores are not independent verification and are NEVER written to model inputs
or historical predictions. Parsing is strict and season/league scoped.
"""
from datetime import datetime, timezone

MAX_SEASON_GAMES = 600
MAX_CLUBS = 30


def iso_utc(value):
    if not isinstance(value, str) or not value:
        raise ValueError("MISSING_KICKOFF")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Only 'matchDateTimeUTC' explicitly documents UTC. Reject other dates.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def derive_scores(rows, *, shortcut, captured):
    """Return safe coverage counts, not a ranked or officially verified league table."""
    if (shortcut not in ("bl1", "bl2", "bl3")
            or not isinstance(rows, list) or len(rows) > MAX_SEASON_GAMES
            or captured.tzinfo is None):
        raise ValueError("INVALID_GERMAN_SEASON_MATCHES")
    played = set()
    scores = {}
    names = {}
    for item in rows:
        if not isinstance(item, dict) or item.get("matchIsFinished") is not True:
            continue
        if item.get("leagueShortcut") not in (None, shortcut):
            continue
        try:
            game_id = item["matchID"]
            if type(game_id) is not int or game_id <= 0:
                continue
            when = iso_utc(item["matchDateTimeUTC"])
            if when > captured:
                continue
            home, away = item["team1"], item["team2"]
            a, b = home["teamId"], away["teamId"]
            if (type(a) is not int or type(b) is not int
                    or a <= 0 or b <= 0 or a == b):
                continue
            an, bn = home["teamName"], away["teamName"]
            if (not isinstance(an, str) or not isinstance(bn, str)
                    or not 1 <= len(an.strip()) <= 130
                    or not 1 <= len(bn.strip()) <= 130):
                continue
            results = item.get("matchResults")
            if not isinstance(results, list) or len(results) > 12:
                continue
            ft = [x for x in results if isinstance(x, dict)
                  and x.get("resultTypeID") == 2]
            if len(ft) != 1:
                continue
            h, v = ft[0].get("pointsTeam1"), ft[0].get("pointsTeam2")
            if (type(h) is not int or type(v) is not int
                    or not 0 <= h <= 30 or not 0 <= v <= 30):
                continue
        except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
            continue
        if game_id in played:
            # Never double-count repeated or contradictory match IDs.
            raise ValueError("DUPLICATE_FINISHED_MATCH_ID")
        if a in names and names[a] != an.strip():
            raise ValueError("CHANGING_TEAM_IDENTITY")
        if b in names and names[b] != bn.strip():
            raise ValueError("CHANGING_TEAM_IDENTITY")
        played.add(game_id)
        names[a], names[b] = an.strip(), bn.strip()
        scores[a] = scores.get(a, 0) + (3 if h > v else 1 if h == v else 0)
        scores[b] = scores.get(b, 0) + (3 if v > h else 1 if h == v else 0)
    if len(names) > MAX_CLUBS:
        raise ValueError("IMPOSSIBLE_TEAM_COUNT")
    return {"season_finished_games_sampled": len(played),
            "derived_clubs_with_points": len(scores),
            "source_points_are_community_unverified": True,
            "official_league_table_confirmed": False,
            "precise_asof_historical_standings_verified": False}
