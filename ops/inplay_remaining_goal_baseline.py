"""Isolated no-network, uncalibrated 90-minute in-play research baseline.

Conditioning a prematch independent Poisson rate on elapsed time is *not*
point-in-time live calibration. This intentionally excludes cards, stoppage,
extra time, tactics, lineups, xG and odds. Never use it to place a bet or to
claim prospective prediction performance. No archived forecasts are edited.
"""
import math
from datetime import datetime, timedelta, timezone

SCHEMA = "football-king-inplay-time-baseline-research-v1"
SCENARIO_ORIGIN = "UNATTESTED_RESEARCH_ASSUMPTION"
RATES = (0.85, 1.0, 1.15)  # predeclared sensitivity, NOT fitted


def _utc(value):
    if type(value) is not str or len(value) > 64:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("NAIVE_TIME")
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("INVALID_TIMESTAMP") from None


def _id(value):
    return (type(value) is str and 1 <= len(value) <= 120
            and value == value.strip() and value.isascii()
            and all(c.isalnum() or c in "_.:-" for c in value))


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _poisson(mu):
    # 46 goals covers the entire allowed intensity domain with negligible tail.
    p = math.exp(-mu)
    weights = [p]
    for k in range(1, 46):
        p *= mu / k
        weights.append(p)
    return weights


def _scenario(home_goals, away_goals, lh, la):
    home, away = _poisson(lh), _poisson(la)
    hw = draw = aw = over25 = over35 = 0.0
    for i, pi in enumerate(home):
        for j, pj in enumerate(away):
            weight = pi * pj
            h, a = home_goals + i, away_goals + j
            if h > a:
                hw += weight
            elif h == a:
                draw += weight
            else:
                aw += weight
            over25 += weight if h + a >= 3 else 0.0
            over35 += weight if h + a >= 4 else 0.0
    return {"home_win": round(hw, 7), "draw": round(draw, 7),
            "away_win": round(aw, 7),
            "over_2_5": round(over25, 7), "over_3_5": round(over35, 7),
            "at_least_one_more_goal": round(-math.expm1(-(lh + la)), 7)}


def evaluate(case):
    """Review an explicitly untrusted hypothetical snapshot; fail closed.

    No self-declared source or time ever upgrades this output to a real-world
    verified prediction. Never pass a success flag onward as model admission.
    """
    hold = {"schema": SCHEMA, "status": "HOLD", "reason": "INVALID_INPUT",
            "production_recommendations": "DISABLED", "model_scoring_eligible": False,
            "probabilities_calibrated": False, "event_source_authenticated": False,
            "point_in_time_externally_attested": False,
            "live_odds_verified": False, "positive_ev_verified": False,
            "recommendation": None, "roi": None, "stakes": None,
            "certified_forward_samples": 0, "scenarios": []}
    try:
        if type(case) is not dict or set(case) != {"fixture", "prematch", "state"}:
            raise ValueError("INVALID_CASE_FIELDS")
        fixture, pre, state = (case[x] for x in ("fixture", "prematch", "state"))
        if (type(fixture) is not dict or set(fixture) !=
                {"fixture_id", "home_id", "away_id", "kickoff_utc"}
                or not all(_id(fixture.get(k)) for k in ("fixture_id", "home_id", "away_id"))
                or fixture["home_id"] == fixture["away_id"]):
            raise ValueError("INVALID_FIXTURE")
        if (type(pre) is not dict or set(pre) !=
                {"home_goals_per_90", "away_goals_per_90", "generated_utc", "origin"}
                or pre.get("origin") != SCENARIO_ORIGIN
                or not _number(pre.get("home_goals_per_90"), .05, 5.5)
                or not _number(pre.get("away_goals_per_90"), .05, 5.5)):
            raise ValueError("INVALID_UNATTESTED_PREMATCH_INPUT")
        if (type(state) is not dict or set(state) !=
                {"fixture_id", "observed_utc", "as_of_utc", "match_status",
                 "elapsed_regulation_minutes", "home_goals", "away_goals",
                 "home_red_cards", "away_red_cards"}
                or state.get("fixture_id") != fixture["fixture_id"]):
            raise ValueError("FIXTURE_IDENTITY_CONFLICT")
        kickoff = _utc(fixture["kickoff_utc"])
        generated = _utc(pre["generated_utc"])
        observed = _utc(state["observed_utc"])
        as_of = _utc(state["as_of_utc"])
        if not timedelta(minutes=10) <= kickoff - generated <= timedelta(days=30):
            raise ValueError("NOT_PROPER_PREMATCH_ASSUMPTION")
        if not timedelta(0) <= as_of - observed <= timedelta(seconds=120):
            raise ValueError("STALE_OR_FUTURE_SNAPSHOT")
        minute = state.get("elapsed_regulation_minutes")
        if (type(minute) not in (int, float) or not math.isfinite(minute)
                or not 0 <= minute < 90
                or state.get("match_status") not in ("FIRST_HALF", "HALF_TIME", "SECOND_HALF")
                or (minute < 45 and state["match_status"] != "FIRST_HALF")
                or (minute == 45 and state["match_status"] != "HALF_TIME")
                or (minute > 45 and state["match_status"] != "SECOND_HALF")
                or not all(type(state.get(k)) is int and 0 <= state[k] <= 20
                           for k in ("home_goals", "away_goals"))
                or not all(type(state.get(k)) is int and 0 <= state[k] <= 5
                           for k in ("home_red_cards", "away_red_cards"))):
            raise ValueError("INVALID_MATCH_STATE")
        wall_minute = (observed - kickoff).total_seconds() / 60
        # Allows a break of <=24m; still refuses snapshots predating match minute.
        if not minute - 4 <= wall_minute <= minute + 24:
            raise ValueError("IMPOSSIBLE_GAME_CLOCK")
        if state["home_red_cards"] or state["away_red_cards"]:
            raise ValueError("RED_CARD_REQUIRES_SEPARATE_UNCALIBRATED_SCENARIO")
        frac = (90 - minute) / 90
        scenarios = []
        for factor in RATES:
            lh = pre["home_goals_per_90"] * frac * factor
            la = pre["away_goals_per_90"] * frac * factor
            scenarios.append({"goal_rate_multiplier": factor,
                              "assumed_remaining_home_goals": round(lh, 6),
                              "assumed_remaining_away_goals": round(la, 6),
                              **_scenario(state["home_goals"], state["away_goals"], lh, la)})
        return {**hold, "status": "RESEARCH_ONLY",
                "reason": "UNATTESTED_UNCALIBRATED_90MIN_TIME_BASELINE_ONLY",
                "fixture_id": fixture["fixture_id"],
                "observed_utc": observed.isoformat(),
                "elapsed_regulation_minutes": minute,
                "existing_score": [state["home_goals"], state["away_goals"]],
                "excludes_stoppage_and_extra_time": True,
                "red_card_state": "BOTH_TEAMS_DECLARED_ZERO_UNAUTHENTICATED",
                "scenarios": scenarios}
    except (ValueError, TypeError, OverflowError, KeyError) as exc:
        return {**hold, "reason": str(exc)}
