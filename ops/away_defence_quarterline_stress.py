"""Fail-closed venue-defence + quarter-line scenario diagnostic (research only).

This audit addresses a specific analytical trap: calling an away defence
"strong" from pooled xGA while ignoring away concessions, then treating a
one-goal home favourite and a two-goal home handicap as interchangeable.

Inputs are self-declared, not independently source authenticated. No results
or hindsight features are permitted, no rates are tuned from a final score,
and no probability or EV can be promoted to a verified recommendation.
"""
import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from asian_handicap_research import _poisson, grade, quarter_units

SCHEMA = "football-king-away-defence-quarterline-stress-v1"
MAX_QUOTE_AGE = timedelta(hours=4)
MIN_KICKOFF_BUFFER = timedelta(minutes=10)
GRADE_PAYOFF = {
    "FULL_WIN": lambda odds: odds - 1,
    "HALF_WIN": lambda odds: (odds - 1) / 2,
    "PUSH": lambda odds: 0.0,
    "HALF_LOSS": lambda odds: -0.5,
    "FULL_LOSS": lambda odds: -1.0,
}


def _need(condition, reason):
    if not condition:
        raise ValueError(reason)


def _utc(value):
    _need(type(value) is str and 0 < len(value) <= 80,
          "INVALID_TIMESTAMP")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    _need(stamp.tzinfo is not None, "NAIVE_TIMESTAMP")
    return stamp.astimezone(timezone.utc)


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _keys(obj, required, optional=frozenset()):
    _need(type(obj) is dict and required <= set(obj)
          and set(obj) <= required | optional, "INVALID_INPUT_FIELDS")


def _id(value):
    return type(value) is str and 1 <= len(value.strip()) <= 120 and value == value.strip()


def _safe_url(value):
    if type(value) is not str or not 1 <= len(value) <= 500:
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and bool(url.hostname)
                and not url.username and not url.password
                and not url.query and not url.fragment and not url.port)
    except ValueError:
        return False


def _matrix(home_rate, away_rate, quote):
    """Enumerate exact independent Poisson scores using the existing AH grader."""
    ph, pa = _poisson(home_rate), _poisson(away_rate)
    mass = {"home_win_2plus": 0.0, "home_win_1": 0.0,
            "draw": 0.0, "away_win": 0.0}
    grades = {name: 0.0 for name in GRADE_PAYOFF}
    for home, p_home in enumerate(ph):
        for away, p_away in enumerate(pa):
            p = p_home * p_away
            margin = home - away
            key = ("home_win_2plus" if margin >= 2 else
                   "home_win_1" if margin == 1 else
                   "draw" if margin == 0 else "away_win")
            mass[key] += p
            if quote is not None:
                outcome = grade(home, away, quote["side"], quote["line"])
                grades[outcome] += p
    _need(abs(math.fsum(mass.values()) - 1) <= 1e-9, "POISSON_MASS_DEFECT")
    ev = None
    if quote is not None:
        odds = quote["decimal_odds"]
        ev = math.fsum(grades[name] * payoff(odds)
                       for name, payoff in GRADE_PAYOFF.items())
    return mass, grades if quote is not None else None, ev


def audit(evidence, *, analysis_utc):
    """Compare immutable *hypothetical* goal-rate scenarios at one time cut.

    Even with a plausible source URL and quote metadata, independent source
    authentication, pre-match time attestation and OOS calibration are absent.
    The returned EVs are ALWAYs scenario diagnostics, NEVER approved bets.
    """
    _keys(evidence, {"fixture", "snapshot", "away_defence", "scenarios"},
          {"quote"})
    fixture = evidence["fixture"]
    _keys(fixture, {"event_id", "home_id", "away_id", "kickoff_utc"})
    _need(all(_id(fixture[key]) for key in ("event_id", "home_id", "away_id"))
          and fixture["home_id"] != fixture["away_id"],
          "INVALID_FIXTURE_IDENTITY")
    kickoff = _utc(fixture["kickoff_utc"])
    analysis = _utc(analysis_utc)
    snap = evidence["snapshot"]
    _keys(snap, {"captured_utc", "source_url"})
    captured = _utc(snap["captured_utc"])
    _need(_safe_url(snap["source_url"]), "INVALID_SOURCE_REFERENCE")
    _need(captured <= analysis <= kickoff - MIN_KICKOFF_BUFFER,
          "UNSAFE_PREMATCH_INPUT_CHRONOLOGY")

    defense = evidence["away_defence"]
    _keys(defense, {"away_games", "away_goals_conceded",
                    "away_clean_sheets", "away_xga_total"})
    n = defense["away_games"]
    ga = defense["away_goals_conceded"]
    cs = defense["away_clean_sheets"]
    xga = defense["away_xga_total"]
    _need(type(n) is int and 1 <= n <= 100
          and type(ga) is int and 0 <= ga <= 20*n
          and type(cs) is int and 0 <= cs <= n
          and _number(xga, 0, 10*n),
          "INVALID_AWAY_DEFENCE_STATS")
    # Conceding 0 goals and registering 0 clean sheets is impossible. Conversely,
    # more clean sheets than non-zero-concession games are not possible.
    _need((ga > 0 or cs == n)
          and cs >= max(0, n - ga), "INCONSISTENT_AWAY_DEFENCE_STATS")
    per_game = ga/n
    xga_per_game = xga/n
    flags = []
    # Prespecified triage labels, NOT tuned using this match's final score.
    if per_game >= 1.5:
        flags.append("AWAY_CONCEDING_HIGH")
    if cs == 0:
        flags.append("AWAY_ZERO_CLEAN_SHEETS")
    if per_game - xga_per_game >= .3:
        flags.append("AWAY_GOALS_EXCEED_XGA")
    if n < 10:
        flags.append("THIN_AWAY_SAMPLE")
    quote = evidence.get("quote")
    quote_status = "NOT_SUPPLIED"
    if quote is not None:
        _keys(quote, {"market", "side", "line", "decimal_odds", "updated_utc"})
        _need(quote["market"] == "asian_handicap"
              and quote["side"] in ("HOME", "AWAY")
              and type(quote["line"]) in (float, int)
              and _number(quote["line"], -5, 5)
              and _number(quote["decimal_odds"], 1.01, 100),
              "INVALID_ASIAN_QUOTE")
        quarter_units(quote["line"])
        updated = _utc(quote["updated_utc"])
        _need(updated <= captured <= analysis,
              "QUOTE_AFTER_SNAPSHOT_OR_ANALYSIS")
        _need(analysis - updated <= MAX_QUOTE_AGE,
              "STALE_QUOTE")
        quote_status = "UNAUTHENTICATED_REFERENCE_NOT_EXECUTABLE"

    scenarios = evidence["scenarios"]
    _need(type(scenarios) is list and 2 <= len(scenarios) <= 8,
          "NEED_MULTIPLE_PREDECLARED_SCENARIOS")
    seen, rows = set(), []
    for scenario in scenarios:
        _keys(scenario, {"scenario_id", "lambda_home", "lambda_away"})
        sid = scenario["scenario_id"]
        _need(_id(sid) and sid not in seen, "INVALID_OR_DUPLICATE_SCENARIO")
        seen.add(sid)
        home_rate, away_rate = scenario["lambda_home"], scenario["lambda_away"]
        _need(_number(home_rate, .1, 5.5) and _number(away_rate, .1, 5.5),
              "INVALID_GOAL_RATE")
        m, grades, ev = _matrix(home_rate, away_rate, quote)
        rows.append({
            "scenario_id": sid,
            "lambda_home": home_rate, "lambda_away": away_rate,
            "margin_probabilities": m,
            "asian_grade_probabilities": grades,
            "quote_ev_per_unit": ev,
            "ev_is_verified": False,
            "rate_model_is_calibrated": False,
        })
    evs = [r["quote_ev_per_unit"] for r in rows
           if r["quote_ev_per_unit"] is not None]
    conflict = any(x > 0 for x in evs) and any(x < 0 for x in evs)
    return {
        "schema": SCHEMA, "status": "HOLD",
        "fixture_id": fixture["event_id"],
        "analysis_utc": analysis.isoformat(),
        "input_capture_utc": captured.isoformat(),
        "away_defence": {
            "away_games": n, "away_goals_conceded_per_game": per_game,
            "away_xga_per_game": xga_per_game,
            "away_clean_sheet_rate": cs/n,
            "risk_flags": flags,
            "risk_flags_are_descriptive_not_calibrated": True,
        },
        "scenario_results": rows,
        "scenarios_disagree_on_ev_sign": conflict,
        "quote_status": quote_status,
        "away_defence_source_independently_verified": False,
        "source_capture_time_independently_attested": False,
        "goal_rates_backtested_out_of_sample": False,
        "asian_quote_authenticated": False,
        "executable_quote_verified": False,
        "validated_positive_ev": False,
        "eligible_for_betting": False,
        "production_recommendations": "DISABLED",
        "notice_zh": (
            "作客防線風險同全贏／贏半拆開審核；每組EV只屬未校準Poisson情景，"
            "來源／時間戳／盤口未獨立驗證，不能事後調權或當作正式投注。"
        ),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--analysis-utc", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    src, dest = Path(args.input), Path(args.output)
    _need(src.resolve() != dest.resolve(), "WILL_NOT_REWRITE_INPUT")
    _need(src.stat().st_size <= 100000, "OVERSIZE_INPUT")
    report = audit(json.loads(src.read_text(encoding="utf-8")),
                   analysis_utc=args.analysis_utc)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False,
                               indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"],
                      "scenarios_disagree_on_ev_sign":
                      report["scenarios_disagree_on_ev_sign"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
