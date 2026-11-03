"""Offline, fail-closed intake of KPL-shaped battle BP evidence.

Research only. This intentionally makes no network requests, does not authenticate
Tencent or provider data, and cannot authorize the data's use or redistribution.
No real match, market, or forecast integration is enabled.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit

OFFICIAL_BATTLE_HOST = "prod.comp.smoba.qq.com"
OFFICIAL_BATTLE_PATH = "/leaguesite/battle/open"
MAX_RAW_BYTES = 128_000
MAX_DRAFT_ACTIONS = 20


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timestamp requires timezone")
    return dt.astimezone(timezone.utc)


def _id(value):
    return isinstance(value, str) and bool(value) and value.strip() == value and len(value) <= 128


def canonical_digest(payload):
    """Integrity of supplied bytes *after JSON parsing*, not authenticity of source."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_RAW_BYTES:
        raise ValueError("oversized payload")
    return hashlib.sha256(encoded).hexdigest()


def _official_battle_url(url, battle_id):
    if not isinstance(url, str) or not _id(battle_id):
        return False
    try:
        parsed = urlsplit(url)
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        return (parsed.scheme == "https" and parsed.hostname == OFFICIAL_BATTLE_HOST
                and parsed.netloc == OFFICIAL_BATTLE_HOST and parsed.path == OFFICIAL_BATTLE_PATH
                and not parsed.fragment and pairs == [("battle_id", battle_id)])
    except (ValueError, TypeError):
        return False


def inspect_offline_battle(payload, match_index, provenance, *, now_utc,
                           previous_games=None, max_age_seconds=180):
    """Return a normalized *untrusted* BP snapshot plus independent failure reasons.

    match_index must come from separately supplied match-list evidence, but its
    origin is NOT authenticated by this function. Even passing all structural
    checks leaves source identity and usage rights unverified => HOLD.

    When the provider grants written data-use rights and an independent trusted
    capture/authentication process is designed, that layer can submit the
    normalized snapshot to PR #390's audit_bp_snapshot. Do not set the
    source_authenticated flag from fields in the incoming payload.
    """
    reasons = []
    if not all(isinstance(x, dict) for x in (payload, match_index, provenance)):
        raise ValueError("payload, match_index and provenance must be objects")
    if previous_games is None:
        previous_games = []
    if not isinstance(previous_games, list):
        raise ValueError("previous_games must be a list")
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be a positive integer")
    try:
        actual_digest = canonical_digest(payload)
    except (TypeError, ValueError, OverflowError, RecursionError):
        actual_digest = None
        reasons.append("INVALID_OR_OVERSIZED_PAYLOAD")
    digest = provenance.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or actual_digest != digest:
        reasons.append("PAYLOAD_DIGEST_MISMATCH")

    league_id, match_id, battle_id = (payload.get(k) for k in ("league_id", "match_id", "battle_id"))
    seq = payload.get("battle_seq")
    if not all(_id(v) for v in (league_id, match_id, battle_id)) or type(seq) is not int or not 1 <= seq <= 7:
        reasons.append("INVALID_BATTLE_IDENTITY")
    team_ids = match_index.get("team_ids")
    expected_battles = match_index.get("battles")
    sides = (payload.get("camp1"), payload.get("camp2"))
    blue_id = sides[0].get("team_id") if isinstance(sides[0], dict) else None
    red_id = sides[1].get("team_id") if isinstance(sides[1], dict) else None
    if (not isinstance(team_ids, list) or len(team_ids) != 2
            or not all(_id(v) for v in team_ids) or len(set(team_ids)) != 2
            or not isinstance(expected_battles, list) or not 1 <= len(expected_battles) <= 7
            or any(not isinstance(x, dict) for x in expected_battles)):
        reasons.append("INVALID_MATCH_INDEX")
    else:
        if (any(type(x.get("battle_seq")) is not int or not _id(x.get("battle_id"))
                or not _id(x.get("blue_team_id")) or not _id(x.get("red_team_id"))
                for x in expected_battles)
                or [x.get("battle_seq") for x in expected_battles] != list(range(1, len(expected_battles) + 1))):
            reasons.append("INVALID_MATCH_INDEX")
        matching = [x for x in expected_battles
                    if x.get("battle_seq") == seq and x.get("battle_id") == battle_id]
        if (match_index.get("league_id") != league_id or match_index.get("match_id") != match_id
                or not all(_id(v) for v in (blue_id, red_id))
                or (all(_id(v) for v in (blue_id, red_id)) and set((blue_id, red_id)) != set(team_ids))
                or len(matching) != 1
                or matching[0].get("blue_team_id") != blue_id
                or matching[0].get("red_team_id") != red_id):
            reasons.append("BATTLE_MATCH_IDENTITY_MISMATCH")
    if not _official_battle_url(provenance.get("source_url"), battle_id):
        reasons.append("SOURCE_URL_NOT_EXACT_OFFICIAL_BATTLE_ROUTE")
    if provenance.get("transport") != "OFFLINE_SUPPLIED_SNAPSHOT":
        reasons.append("NETWORK_CAPTURE_NOT_SUPPORTED")
    try:
        pub = _utc(provenance.get("published_at"))
        seen = _utc(provenance.get("observed_at"))
        now = _utc(now_utc)
        if pub > seen:
            reasons.append("PUBLICATION_AFTER_CAPTURE")
        if seen > now:
            reasons.append("FUTURE_CAPTURE")
        if (now - seen).total_seconds() > max_age_seconds:
            reasons.append("STALE_CAPTURE")
    except (TypeError, ValueError):
        reasons.append("INVALID_PROVENANCE_CLOCK")

    raw_bp = payload.get("bp_list")
    picks = {team: [] for team in team_ids} if isinstance(team_ids, list) and len(team_ids) == 2 and all(_id(v) for v in team_ids) and len(set(team_ids)) == 2 else {}
    bans = {team: [] for team in picks}
    if (not isinstance(raw_bp, list) or len(raw_bp) not in (18, 20)
            or len(raw_bp) > MAX_DRAFT_ACTIONS or len(picks) != 2
            or not all(_id(v) for v in (blue_id, red_id))):
        reasons.append("INCOMPLETE_OR_INVALID_BP")
    else:
        actions_ok = True
        heroes_seen = set()
        for item in raw_bp:
            if not isinstance(item, dict):
                actions_ok = False
                break
            camp = item.get("camp")
            action = item.get("is_ban_or_pick")
            hero = item.get("hero_id")
            if (type(camp) is not int or camp not in (1, 2) or type(action) is not int
                    or action not in (0, 1) or type(hero) not in (str, int) or isinstance(hero, bool)):
                actions_ok = False
                break
            hero = str(hero)
            if not _id(hero) or hero in heroes_seen:
                actions_ok = False
                break
            heroes_seen.add(hero)
            team = blue_id if camp == 1 else red_id
            (bans if action == 0 else picks)[team].append(hero)
        if (not actions_ok or sorted(map(len, picks.values())) != [5, 5]
                or sorted(map(len, bans.values())) not in ([4, 4], [5, 5])):
            reasons.append("INCOMPLETE_OR_INVALID_BP")

    prev_used = {team: set() for team in picks}
    if type(seq) is int and 1 <= seq <= 7:
        if len(previous_games) != seq - 1:
            reasons.append("INCOMPLETE_PRIOR_GAMES")
        else:
            for n, game in enumerate(previous_games, 1):
                if (not isinstance(game, dict) or game.get("event_id") != match_id
                        or game.get("game_number") != n
                        or game.get("team_ids") != team_ids
                        or not isinstance(game.get("picks_by_team"), dict)
                        or set(game["picks_by_team"]) != set(prev_used)):
                    reasons.append("INVALID_PRIOR_GAME_IDENTITY")
                    break
                for team in prev_used:
                    heroes = game["picks_by_team"][team]
                    if (not isinstance(heroes, list) or len(heroes) != 5
                            or any(not _id(v) for v in heroes) or len(set(heroes)) != 5
                            or prev_used[team].intersection(heroes)):
                        reasons.append("INVALID_PRIOR_GAME_PICKS")
                        break
                    prev_used[team].update(heroes)
                if "INVALID_PRIOR_GAME_PICKS" in reasons:
                    break
            if seq < 7 and "INCOMPLETE_OR_INVALID_BP" not in reasons:
                if any(prev_used[team].intersection(picks[team]) for team in prev_used):
                    reasons.append("OWN_HERO_REUSE")

    snapshot = None
    if not reasons:
        # Original event/team IDs retained. This snapshot may be STRUCTURALLY
        # correct; it has NOT been externally authenticated or licensed.
        snapshot = {"event_id": match_id, "game_number": seq,
                    "team_ids": team_ids,
                    "side_by_team": {blue_id: "blue", red_id: "red"},
                    "picks_by_team": picks, "bans_by_team": bans,
                    "bp_complete": True, "source": provenance["source_url"],
                    "source_authenticated": False,
                    "published_at": provenance["published_at"],
                    "observed_at": provenance["observed_at"]}
    return {"status": "HOLD", "structural_validation_passed": not reasons,
            "reasons": reasons or ["SOURCE_AUTHENTICITY_AND_RIGHTS_NOT_INDEPENDENTLY_VERIFIED"],
            "normalized_snapshot": snapshot,
            "independent_match_authentication_verified": False,
            "provider_data_usage_rights_verified": False,
            "research_only": True, "live_execution_allowed": False,
            "network_requests_made": 0}
