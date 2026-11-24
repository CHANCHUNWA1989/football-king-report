"""Frozen ORIGINAL six-league Poisson predictor from main before PR #465.

Source repository: CHANCHUNWA1989/football-king-report
Pinned source-file Git blob SHA-1: 5216a97e5fac69bd0d0594f28e3b35778f36c62c
Frozen solely to compare pre-match source alias fragmentation against the
new canonical-ID predictor on the SAME input. No outcome, quote or EV input.
Do not edit this module when editing the challenger. Never promotes betting.
"""
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SOURCE_BLOB = "5216a97e5fac69bd0d0594f28e3b35778f36c62c"
MODEL_ROLE = "FROZEN_LEGACY_IDENTITY_POISSON_RESEARCH"
HK = ZoneInfo("Asia/Hong_Kong")

def poisson_1x2(home_rate, away_rate):
    if not all(math.isfinite(x) and 0.1 <= x <= 5.5 for x in (home_rate, away_rate)):
        raise ValueError("MODEL_RATE_OUT_OF_RANGE")
    h = [math.exp(-home_rate) * home_rate**i / math.factorial(i) for i in range(12)]
    a = [math.exp(-away_rate) * away_rate**i / math.factorial(i) for i in range(12)]
    values = [0.0, 0.0, 0.0]
    for i, hi in enumerate(h):
        for j, aj in enumerate(a):
            values[0 if i > j else 1 if i == j else 2] += hi * aj
    total = sum(values)
    return [round(x / total, 7) for x in values]


def _utc(s):
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_KICKOFF")
    return dt.astimezone(timezone.utc)


def predict_league(rows, league, now):
    """Return only genuinely pre-kickoff fixtures, with training data prior to today."""
    today = now.astimezone(HK).date()
    history, scheduled = [], []
    seen = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        h, a = row.get("home"), row.get("away")
        if not all(isinstance(t, str) and t and len(t) < 110 for t in (h, a)) or h == a:
            continue
        try:
            match_day = date.fromisoformat(row["date"])
        except (KeyError, ValueError, TypeError):
            continue
        score = row.get("score_ft")
        if (match_day < today and row.get("status") == "FINISHED"
                and isinstance(score, list) and len(score) == 2
                and all(type(x) is int and 0 <= x <= 20 for x in score)):
            history.append((match_day, h, a, score[0], score[1]))
        kickoff = row.get("kickoff_utc")
        if not kickoff or score is not None or row.get("status") != "SCHEDULED":
            continue
        try:
            dt = _utc(kickoff)
        except (ValueError, TypeError):
            continue
        if (dt.astimezone(HK).date() != match_day
                or not (now + timedelta(minutes=10) < dt)
                or match_day > today + timedelta(days=21)):
            continue
        event_id = str(row.get("event_id") or league + "|" + match_day.isoformat() + "|" + h + "|" + a)
        candidate = (dt, event_id, h, a, row.get("schedule_utc_source"))
        if event_id in seen:
            if seen[event_id][:4] != candidate[:4]:
                return []  # conflicting fixture identity or kickoff
            continue
        seen[event_id] = candidate
        scheduled.append(candidate)
    # Never train on duplicated source rows or conflicting revisions of the same fixture.
    # A duplicated result must not artificially increase the training sample.
    unique_history = {}
    for item in history:
        key = (item[0], item[1], item[2])
        if key in unique_history and unique_history[key] != item:
            return []  # conflicting scores: fail closed for this league
        unique_history[key] = item
    history = list(unique_history.values())
    if len(history) < 30:
        return []
    team_appearances = defaultdict(int)
    home_for = defaultdict(list)
    away_for = defaultdict(list)
    for _, h, a, gh, ga in history:
        team_appearances[h] += 1
        team_appearances[a] += 1
        home_for[h].append((gh, ga))
        away_for[a].append((ga, gh))
    league_home = max(0.3, sum(r[3] for r in history) / len(history))
    league_away = max(0.3, sum(r[4] for r in history) / len(history))
    raw_history = json.dumps(sorted(history), ensure_ascii=False, default=str).encode("utf-8")
    digest = hashlib.sha256(raw_history).hexdigest()
    predictions = []
    prior = 6
    for ko, event_id, h, a, schedule_source in sorted(scheduled):
        if team_appearances[h] < 3 or team_appearances[a] < 3:
            continue
        def mean_role(team, group, i, average):
            values = group[team]
            return (sum(x[i] for x in values) + prior * average) / (len(values) + prior)
        h_attack = mean_role(h, home_for, 0, league_home)
        a_defense = mean_role(a, away_for, 1, league_home)
        a_attack = mean_role(a, away_for, 0, league_away)
        h_defense = mean_role(h, home_for, 1, league_away)
        expected_home = min(5.5, max(0.1, h_attack * a_defense / league_home))
        expected_away = min(5.5, max(0.1, a_attack * h_defense / league_away))
        probabilities = poisson_1x2(expected_home, expected_away)
        predictions.append({
            "league": league, "event_id": event_id, "home": h, "away": a,
            "kickoff_utc": ko.isoformat(), "prediction_utc": now.isoformat(),
            "model": "poisson-shrinkage-unvalidated-v4.1",
            "training_games": len(history), "training_cutoff_local_day": (today - timedelta(days=1)).isoformat(),
            "training_observations_sha256": digest,
            "p_home": probabilities[0], "p_draw": probabilities[1], "p_away": probabilities[2],
            "expected_home_goals": round(expected_home, 5),
            "expected_away_goals": round(expected_away, 5),
            "schedule_utc_source": schedule_source or "original_fixture_gateway",
            "schedule_time_agreement_only_not_result_verification": bool(schedule_source),
            "calibrated": False, "verified_market_odds": False,
            "production_recommendations": "DISABLED",
        })
    return predictions

