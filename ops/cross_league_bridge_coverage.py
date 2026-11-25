"""Cross-league research coverage gate, not a league strength estimator.

Domestic scores alone cannot identify cross-league relative strength.
Only claimed prior FT90 international club fixtures connect leagues.
No provider calls, odds, model fit, or authorization.
"""
from collections import Counter, defaultdict
from datetime import datetime
import re

IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
MIN_BRIDGE_MATCHES = 10  # research design, not a calibrated threshold
MIN_CLUBS_PER_LEAGUE = 3
MAX_ROWS = 6000


def _id(value):
    if type(value) is not str or not IDENTIFIER.fullmatch(value):
        raise ValueError("INVALID_NATIVE_ID_CLAIM")
    return value


def _time(value):
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError("UTC_REQUIRED")
    stamp = datetime.fromisoformat(value[:-1] + "+00:00")
    if stamp.utcoffset() is None:
        raise ValueError("UTC_REQUIRED")
    return stamp


def audit_bridges(rows, *, league_a, league_b, as_of_utc):
    a, b = _id(league_a), _id(league_b)
    cutoff = _time(as_of_utc)
    if a == b or type(rows) is not list or len(rows) > MAX_ROWS:
        raise ValueError("INVALID_CROSS_LEAGUE_COHORT")
    seen = set()
    physical = set()
    by_pair = Counter()
    clubs = defaultdict(set)
    home_counts = defaultdict(Counter)
    graph = defaultdict(set)
    required = {"fixture_id", "source_namespace", "home_team_id", "away_team_id",
                "home_league_id", "away_league_id", "kickoff_utc",
                "result_observed_utc", "home_goals", "away_goals", "venue",
                "competition_kind", "score_scope"}
    # Single namespace is required to avoid counting the same physical match
    # from two providers as independent games. IDs remain untrusted claims.
    namespaces = set()
    for row in rows:
        if type(row) is not dict or set(row) != required:
            raise ValueError("INVALID_BRIDGE_ROW")
        fixture, source, h, v, hl, vl = map(_id, (
            row["fixture_id"], row["source_namespace"], row["home_team_id"],
            row["away_team_id"], row["home_league_id"], row["away_league_id"]))
        namespaces.add(source)
        if len(namespaces) > 1:
            raise ValueError("MIXED_SOURCE_NAMESPACES")
        ko, observed = map(_time, (row["kickoff_utc"], row["result_observed_utc"]))
        if not ko < observed < cutoff:
            raise ValueError("RESULT_TIME_LEAKAGE")
        key = (ko, tuple(sorted((h, v))))
        if fixture in seen or key in physical or h == v:
            raise ValueError("DUPLICATE_OR_INVALID_FIXTURE")
        seen.add(fixture)
        physical.add(key)
        if (row["score_scope"] != "FT90"
                or row["venue"] not in ("HOME", "NEUTRAL")
                or any(type(row[k]) is not int or not 0 <= row[k] <= 20
                       for k in ("home_goals", "away_goals"))):
            raise ValueError("INVALID_SCORE_OR_VENUE")
        if row["competition_kind"] == "DOMESTIC" and hl == vl:
            continue
        if row["competition_kind"] != "INTERNATIONAL_CLUB" or hl == vl:
            raise ValueError("INVALID_COMPETITION_KIND_OR_LEAGUE")
        pair = tuple(sorted((hl, vl)))
        by_pair[pair] += 1
        clubs[pair, hl].add(h)
        clubs[pair, vl].add(v)
        home_counts[pair][hl if row["venue"] == "HOME" else "NEUTRAL"] += 1
        graph[hl].add(vl)
        graph[vl].add(hl)

    connected, pending = set(), [a]
    while pending:
        node = pending.pop()
        if node not in connected:
            connected.add(node)
            pending.extend(graph[node] - connected)
    pair = tuple(sorted((a, b)))
    n = by_pair[pair]
    counts = {league: len(clubs[pair, league]) for league in pair}
    venues = {league: home_counts[pair][league] for league in pair}
    venues["NEUTRAL"] = home_counts[pair]["NEUTRAL"]
    enough = (n >= MIN_BRIDGE_MATCHES and min(counts.values()) >= MIN_CLUBS_PER_LEAGUE
              and all(venues[x] > 0 for x in pair))
    reason = ("UNCONNECTED_LEAGUES" if b not in connected else
              "INSUFFICIENT_DIRECT_BRIDGE_COVERAGE" if not enough else
              "CLAIMED_COVERAGE_ONLY_NO_AUTHENTICATION_OR_FIT")
    return {"status": "HOLD", "reason": reason, "production_recommendations": "DISABLED",
            "direct_bridge_matches": n, "claimed_connected": b in connected,
            "distinct_clubs_by_league": counts, "venue_counts": venues,
            "research_coverage_threshold_met": enough,
            "source_identity_authenticated": False, "league_membership_authenticated": False,
            "source_rights_verified": False, "calibrated": False,
            "strength_multiplier": None, "certified_prospective_samples": 0}
