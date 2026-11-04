"""KPL full-global-BP snapshot evidence gate (research only).

Validates input structure and source clocks, not external source authenticity.
No model probabilities, recommendations, network calls, or order placement.
"""
from __future__ import annotations

from datetime import datetime
from shared.source_freshness import check_source


def _ids(value, count=None):
    return (isinstance(value, list) and (count is None or len(value) == count)
            and all(isinstance(v, str) and v.strip() and v == v.strip() for v in value)
            and len(value) == len(set(value)))


def _time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp not string")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone missing")
    return dt


def audit_bp_snapshot(snapshot, previous_games, *, now_utc, max_age_seconds=120):
    """Fail closed for a single game: complete attested history needed for games 2–7.

    source_authenticated is an EXTERNAL assertion, not verified by this function.
    Each previous_games item must be separately attested and match the same event.
    Game 7 permits hero reuse (peak duel) but still requires preceding history.
    """
    reasons = []
    if not isinstance(snapshot, dict) or not isinstance(previous_games, list):
        raise ValueError("snapshot object and previous_games list required")
    event = snapshot.get("event_id")
    game = snapshot.get("game_number")
    teams = snapshot.get("team_ids")
    if not isinstance(event, str) or not event.strip(): reasons.append("MISSING_EVENT_ID")
    if type(game) is not int or not 1 <= game <= 7: reasons.append("INVALID_GAME_NUMBER")
    if not _ids(teams, 2): reasons.append("INVALID_TEAM_IDS")
    if snapshot.get("bp_complete") is not True: reasons.append("INCOMPLETE_BP")
    if snapshot.get("source_authenticated") is not True: reasons.append("SOURCE_AUTHENTICATION_MISSING")
    if not isinstance(snapshot.get("source"), str) or not snapshot["source"].strip():
        reasons.append("MISSING_SOURCE")
    sides, picks, bans = (snapshot.get(k) for k in ("side_by_team", "picks_by_team", "bans_by_team"))
    teamset = set(teams) if _ids(teams, 2) else set()
    if (not isinstance(sides, dict) or set(sides) != teamset
            or not all(isinstance(v, str) for v in sides.values())
            or set(sides.values()) != {"blue", "red"}):
        reasons.append("INVALID_SIDES")
    if not isinstance(picks, dict) or set(picks) != teamset or not all(_ids(v, 5) for v in picks.values()):
        reasons.append("INVALID_PICKS")
    if not isinstance(bans, dict) or set(bans) != teamset or not all(_ids(v) for v in bans.values()):
        reasons.append("INVALID_BANS")
    if "INVALID_PICKS" not in reasons and "INVALID_BANS" not in reasons:
        all_picks = [hero for heroes in picks.values() for hero in heroes]
        all_bans = [hero for heroes in bans.values() for hero in heroes]
        if len(all_picks) != len(set(all_picks)): reasons.append("CROSS_TEAM_PICK_DUPLICATE")
        if len(all_bans) != len(set(all_bans)) or set(all_picks).intersection(all_bans):
            reasons.append("PICK_BAN_CONFLICT")
    if "INVALID_GAME_NUMBER" not in reasons:
        if (len(previous_games) != game - 1
                or [r.get("game_number") if isinstance(r, dict) else None
                    for r in previous_games] != list(range(1, game))):
            reasons.append("HISTORY_INCOMPLETE_OR_UNORDERED")
        else:
            used = {team: set() for team in teamset}
            for prev in previous_games:
                prev_picks = prev.get("picks_by_team")
                if (prev.get("event_id") != event or prev.get("team_ids") != teams
                        or prev.get("bp_complete") is not True
                        or prev.get("source_authenticated") is not True
                        or not isinstance(prev_picks, dict) or set(prev_picks) != teamset
                        or not all(_ids(v, 5) for v in prev_picks.values())):
                    reasons.append("UNVERIFIED_OR_INVALID_HISTORY")
                    break
                for team in teamset:
                    if used[team].intersection(prev_picks[team]):
                        reasons.append("PRIOR_HERO_REUSE")
                    used[team].update(prev_picks[team])
            if game < 7 and "INVALID_PICKS" not in reasons:
                for team in teamset:
                    if used[team].intersection(picks[team]):
                        reasons.append("OWN_HERO_REUSE")
    try:
        if _time(snapshot.get("published_at")) > _time(snapshot.get("observed_at")):
            reasons.append("PUBLICATION_AFTER_CAPTURE")
        fresh = check_source(snapshot.get("source"), snapshot.get("observed_at"),
                             now_utc, max_age_seconds)
        reasons.extend(fresh["reasons"])
    except (ValueError, TypeError):
        reasons.append("INVALID_SOURCE_CLOCK")
    return {"status": "VALIDATED_RESEARCH_INPUT" if not reasons else "HOLD",
            "reasons": list(dict.fromkeys(reasons)),
            "external_authentication_not_proven_by_code": True,
            "research_only": True, "live_execution_allowed": False}
