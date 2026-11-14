"""Bounded goal-market reconstruction from the original sealed A goal rates.

The original shadow stores rounded rates, not a sealed Asian/totals forecast.
This pure calculation is retrospective research, not authenticated outcomes,
offered bookmaker lines, a calibrated model, or new prospective evidence.

BTTS, exact-score and result-market queries adapted from penaltyblog FootballProbabilityGrid,
Copyright 2021 Martin Eastwood (MIT); third_party/penaltyblog/LICENCE.
"""
from collections import defaultdict
from datetime import date, timedelta
import math
import re
from zoneinfo import ZoneInfo

from ops import case_fourway_scoring
from ops.asian_handicap_research import MAX_GOALS, TYPES, _poisson
from ops.shadow_forecast import poisson_1x2
from ops.source_fixture_identity import validate_sealed_identity


SOURCE_MODEL = "poisson-shrinkage-unvalidated-v4.1"
DERIVED_MODEL = "sealed-rate-poisson-goal-market-reconstruction-v1"
AH_UNITS = tuple(range(-20, 21))
TOTAL_UNITS = tuple(range(41))
HK = ZoneInfo("Asia/Hong_Kong")


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _raw_poisson(rate, maximum):
    terms = [math.exp(-rate)]
    for goals in range(1, maximum + 1):
        terms.append(terms[-1] * rate / goals)
    return terms


def _tail_bound(rate):
    # Beyond MAX_GOALS the ratio decreases, so the geometric series bounds
    # all omitted terms; the small numerical allowance is reported as well.
    first = _raw_poisson(rate, MAX_GOALS + 1)[-1]
    return first / (1 - rate / (MAX_GOALS + 2))


def _grade(margin, quarter_units):
    # Integer quarter units avoid float ties and support total lines to 10,
    # score totals to 60, and FT margins to 30 without the older AH score cap.
    halves = ((quarter_units, quarter_units) if quarter_units % 2 == 0
              else (quarter_units - 1, quarter_units + 1))
    net = sum(1 if 4 * margin + half > 0 else -1 if 4 * margin + half < 0 else 0
              for half in halves)
    return {2: "FULL_WIN", 1: "HALF_WIN", 0: "PUSH",
            -1: "HALF_LOSS", -2: "FULL_LOSS"}[net]


def _projection(distribution, side, units, actual, *, totals=False):
    weights = {name: [] for name in TYPES}
    reverse = side in ("AWAY", "UNDER")
    signed_units = -units if totals and side == "OVER" else units
    for value, probability in distribution.items():
        margin = -value if reverse else value
        weights[_grade(margin, signed_units)].append(probability)
    probabilities = {name: math.fsum(weights[name]) for name in TYPES}
    observed = _grade(-actual if reverse else actual, signed_units)
    return {"side": side, "line": units / 4,
            "grade_probabilities": probabilities, "observed_grade_candidate": observed,
            "log_loss": -math.log(max(probabilities[observed], 1e-15)),
            "brier": math.fsum((probability - int(name == observed)) ** 2
                               for name, probability in probabilities.items())}


def _forecast(pair, forecast):
    _require(type(forecast) is dict, "INVALID_GOAL_FORECAST")
    _require(forecast.get("production_recommendations") == "DISABLED"
             and forecast.get("calibrated") is False
             and forecast.get("verified_market_odds") is False
             and all(forecast.get(field) is None for field in ("result", "historical_outcome", "score_ft", "y"))
             and all(field not in forecast or forecast[field] is False for field in (
                 "independently_verified", "eligible_for_model_scoring", "eligible_for_betting_promotion",
                 "ready_for_production", "automatic_bets", "results_independently_verified")),
             "UNSAFE_GOAL_FORECAST")
    _require(forecast.get("event_id") == pair["forecast_event_id"]
             and ("forecast_event_id" not in forecast
                  or forecast["forecast_event_id"] == forecast["event_id"])
             and all(forecast.get(field) == pair[field] for field in (
                 "league", "home", "away", "kickoff_utc", "prediction_utc")),
             "GOAL_FORECAST_IDENTITY_MISMATCH")
    original = [forecast.get(field) for field in ("p_home", "p_draw", "p_away")]
    _require(all(type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)
                 for value in original) and original == pair["model"],
             "GOAL_FORECAST_IDENTITY_MISMATCH")
    try:
        validate_sealed_identity(forecast)
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ValueError("GOAL_FORECAST_IDENTITY_MISMATCH") from None
    _require(forecast.get("model") == SOURCE_MODEL
             and type(forecast.get("training_games")) is int and forecast["training_games"] >= 30
             and type(forecast.get("training_observations_sha256")) is str
             and re.fullmatch("[0-9a-f]{64}", forecast["training_observations_sha256"]),
             "INVALID_SEALED_GOAL_MODEL_METADATA")
    try:
        cutoff = date.fromisoformat(forecast["training_cutoff_local_day"])
        prediction = case_fourway_scoring._utc(pair["prediction_utc"])
        _require(cutoff == prediction.astimezone(HK).date() - timedelta(days=1),
                 "INVALID_SEALED_GOAL_MODEL_METADATA")
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ValueError("INVALID_SEALED_GOAL_MODEL_METADATA") from None
    rates = [forecast.get(field) for field in ("expected_home_goals", "expected_away_goals")]
    _require(all(type(value) in (int, float) and .1 <= value <= 5.5 and math.isfinite(value)
                 for value in rates), "INVALID_SEALED_GOAL_RATES")
    return rates


def score_goal_markets(pair, forecast, score_ft):
    """Return all fixed AH/totals scenarios from A rates; never certify them."""
    case_fourway_scoring.score_case(pair, score_ft)
    home_rate, away_rate = _forecast(pair, forecast)
    original_replay = poisson_1x2(home_rate, away_rate)
    # Each stored rate is rounded to five decimals; original probabilities
    # were calculated before that rounding. A product-Poisson coupling and
    # conditioning bound accommodates that loss, plus 7dp output rounding.
    minimum_original_mass = math.fsum(_raw_poisson(5.5, 11)) ** 2
    tolerance = 2 * (2 * .000005) / minimum_original_mass + .0000001
    replay_gap = max(abs(value - original) for value, original in zip(original_replay, pair["model"]))
    _require(replay_gap <= tolerance, "SEALED_RATE_PROBABILITY_CONFLICT")
    home, away = _poisson(home_rate), _poisson(away_rate)
    margins, totals = defaultdict(list), defaultdict(list)
    btts_mass = []
    scorelines = []
    for home_goals, home_probability in enumerate(home):
        for away_goals, away_probability in enumerate(away):
            probability = home_probability * away_probability
            scorelines.append((home_goals, away_goals, probability))
            margins[home_goals - away_goals].append(probability)
            totals[home_goals + away_goals].append(probability)
            if home_goals > 0 and away_goals > 0:
                btts_mass.append(probability)
    margin_mass = {margin: math.fsum(values) for margin, values in margins.items()}
    total_mass = {total: math.fsum(values) for total, values in totals.items()}
    rebuilt_1x2 = [math.fsum(probability for margin, probability in margin_mass.items() if margin > 0),
                   margin_mass[0],
                   math.fsum(probability for margin, probability in margin_mass.items() if margin < 0)]
    raw_mass = math.fsum(_raw_poisson(home_rate, MAX_GOALS)) * math.fsum(_raw_poisson(away_rate, MAX_GOALS))
    btts_yes = math.fsum(btts_mass)
    btts_probabilities = {"YES": btts_yes, "NO": 1.0 - btts_yes}
    observed_yes = int(score_ft[0] > 0 and score_ft[1] > 0)
    btts_outcome = "YES" if observed_yes else "NO"
    # Rank raw cell probabilities, with deterministic ordering of exact ties.
    # The top five retain their original mass; they are not an exhaustive grid.
    top_scores = sorted(scorelines, key=lambda cell: (-cell[2], cell[0], cell[1]))[:5]
    top_mass = math.fsum(cell[2] for cell in top_scores)
    score_in_grid = score_ft[0] <= MAX_GOALS and score_ft[1] <= MAX_GOALS
    exact_probability = home[score_ft[0]] * away[score_ft[1]] if score_in_grid else None
    handicap_projections = [_projection(margin_mass, side, units, score_ft[0] - score_ft[1])
                            for side in ("HOME", "AWAY") for units in AH_UNITS]
    # Draw-no-bet is the existing zero-handicap settlement, not a new grader.
    draw_no_bet = {}
    for row in handicap_projections:
        if row["line"] != 0:
            continue
        p = row["grade_probabilities"]
        no_push = p["FULL_WIN"] + p["FULL_LOSS"]
        draw_no_bet[row["side"]] = {
            "full_win_probability": p["FULL_WIN"], "push_probability": p["PUSH"],
            "full_loss_probability": p["FULL_LOSS"],
            "conditional_win_probability_given_no_push": p["FULL_WIN"] / no_push if no_push > 0 else None,
            "observed_grade_candidate": row["observed_grade_candidate"],
        }
    ph, pd, pa = rebuilt_1x2
    return {
        "schema": "football-king-case-goal-market-reconstruction-v1",
        "status": "HOLD", "production_recommendations": "DISABLED",
        "candidate_only": True, "certified_case_count": 0,
        "derived_reconstruction": True, "derived_model_id": DERIVED_MODEL,
        "distribution_sealed_pre_match": False,
        "independently_verified": False, "eligible_for_model_scoring": False,
        "eligible_for_betting_promotion": False, "results_independently_verified": False,
        "offered_handicap_line_authenticated": False, "offered_totals_line_authenticated": False,
        "offered_decimal_odds_authenticated": False, "probability_calibration_verified": False,
        "positive_expected_value_verified": False, "B_C_market_goal_distributions_available": False,
        "original_1x2_preserved": True, "derived_review_not_a_trust_input": True,
        "case_id": pair["case_id"], "forecast_event_id": pair["forecast_event_id"],
        "score_ft_candidate": list(score_ft), "market_projection_count": 164,
        "market_projection_count_basis": "AH_TOTALS_FIXED_SCENARIOS",
        "result_market_diagnostics": {
            "status": "HOLD", "production_recommendations": "DISABLED",
            "basis": "DERIVED_INDEPENDENT_POISSON_GRID",
            "double_chance": {"1X": ph + pd, "X2": pd + pa, "12": ph + pa},
            "double_chance_markets_overlap": True,
            "double_chance_occurs_in_candidate": {
                "1X": score_ft[0] >= score_ft[1], "X2": score_ft[0] <= score_ft[1],
                "12": score_ft[0] != score_ft[1]},
            "draw_no_bet": draw_no_bet,
            "forecast_sealed_pre_match": False, "offered_market_authenticated": False,
            "calibration_verified": False, "results_independently_verified": False,
            "positive_ev_verified": False,
        },
        "correct_score_diagnostic": {
            "status": "HOLD", "production_recommendations": "DISABLED",
            "basis": "DERIVED_INDEPENDENT_POISSON_GRID",
            "probabilities_conditioned_on_truncation": True,
            "top_k": 5,
            "top_scorelines": [{"home_goals": h, "away_goals": a, "probability": p}
                               for h, a, p in top_scores],
            "top_scorelines_probability_mass": top_mass,
            "other_in_grid_probability_mass": 1.0 - top_mass,
            "candidate_score_in_grid": score_in_grid,
            "candidate_score_probability": exact_probability,
            "candidate_score_log_loss": -math.log(exact_probability) if score_in_grid else None,
            "candidate_score_reason": ("IN_RETAINED_SCORE_GRID" if score_in_grid
                                       else "OUTSIDE_RETAINED_SCORE_GRID"),
            "forecast_sealed_pre_match": False, "offered_market_authenticated": False,
            "calibration_verified": False, "results_independently_verified": False,
            "positive_ev_verified": False,
        },
        "both_teams_to_score": {
            "status": "HOLD", "production_recommendations": "DISABLED",
            "probabilities": btts_probabilities,
            "observed_outcome_candidate": btts_outcome,
            "binary_brier": (btts_yes - observed_yes) ** 2,
            "log_loss": -math.log(max(btts_probabilities[btts_outcome], 1e-15)),
            "basis": "DERIVED_INDEPENDENT_POISSON_GRID",
            "forecast_sealed_pre_match": False, "offered_market_authenticated": False,
            "calibration_verified": False, "results_independently_verified": False,
            "positive_ev_verified": False,
        },
        "distribution_diagnostics": {
            "source_model_id": SOURCE_MODEL, "source_model": "A",
            "sealed_expected_home_goals": home_rate, "sealed_expected_away_goals": away_rate,
            "training_games": forecast["training_games"],
            "training_cutoff_local_day": forecast["training_cutoff_local_day"],
            "training_observations_sha256": forecast["training_observations_sha256"],
            "source_rate_rounding_decimals": 5,
            "original_A_probabilities": list(pair["model"]),
            "original_12_goal_grid_replay": original_replay,
            "reconstructed_1x2_from_distribution": rebuilt_1x2,
            "max_original_rate_replay_gap": replay_gap,
            "rate_rounding_consistency_tolerance": tolerance,
            "max_expanded_distribution_gap_from_original_A": max(
                abs(value - original) for value, original in zip(rebuilt_1x2, pair["model"])),
            "grid_max_goals_each": MAX_GOALS,
            "probabilities_conditioned_on_truncation": True,
            "retained_joint_mass_before_conditioning": min(1.0, max(0.0, raw_mass)),
            "omitted_joint_mass_estimate": max(0.0, 1 - raw_mass),
            "omitted_joint_mass_upper_bound": _tail_bound(home_rate) + _tail_bound(away_rate) + 16 * math.ulp(1.0),
        },
        "asian_handicap": handicap_projections,
        "totals": [_projection(total_mass, side, units, sum(score_ft), totals=True)
                   for side in ("OVER", "UNDER") for units in TOTAL_UNITS],
        "notice": "原A封存入球率衍生嘅固定全格研究重建；不是原封存盤口預測、獨立認證或可下注賠率。",
    }
