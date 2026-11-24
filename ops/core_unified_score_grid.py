"""Unified *research* score grid: one distribution for mutually consistent markets.

This is a NEW challenger, not A/B/C, the sealed Dixon-Coles forward pilot,
a validated A-League model, official xG, a betting signal, or a live odds feed.
No input contains results, bookmaker prices, or a learning process. The rho
parameter is fixed in this module; never tune it after observing a match.
"""
import math

from ops.asian_handicap_research import grade, split_lines

MODEL = "unified-score-grid-fixed-dc-minus005-research-v1"
MAX_GOALS = 24
RHO = -0.05
ALLOWED_RHO = (0.0, RHO)
GRADES = ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")
THREEWAY = ("HOME", "DRAW", "AWAY")


def _valid_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _poisson(rate):
    if not _valid_number(rate) or not 0.1 <= rate <= 5.5:
        raise ValueError("INVALID_OR_UNVERIFIED_GOAL_RATE")
    weights = [math.exp(-rate)]
    for goals in range(1, MAX_GOALS + 1):
        weights.append(weights[-1] * rate / goals)
    mass = math.fsum(weights)
    if not .99999999 <= mass <= 1.00000001:
        raise ValueError("GOAL_GRID_TRUNCATION_EXCEEDS_BOUND")
    return weights, max(0.0, 1.0 - mass)


def score_grid(home_rate, away_rate, *, rho=RHO):
    """Normalized 25x25 score matrix with four-cell Dixon-Coles correction.

    The 0..24 grid keeps truncation tiny even for a 5.5-goal rate. No
    in-play minute, red card, HT or next-goal hazard is inferred here.
    """
    h, h_tail = _poisson(home_rate)
    a, a_tail = _poisson(away_rate)
    if not _valid_number(rho) or rho not in ALLOWED_RHO:
        raise ValueError("UNDECLARED_DIXON_COLES_RHO")
    tau = {
        (0, 0): 1 - home_rate * away_rate * rho,
        (0, 1): 1 + home_rate * rho,
        (1, 0): 1 + away_rate * rho,
        (1, 1): 1 - rho,
    }
    if not all(_valid_number(x) and x > 0 for x in tau.values()):
        raise ValueError("INVALID_DIXON_COLES_LOW_SCORE_MASS")
    raw = [[hp * ap * tau.get((i, j), 1.0) for j, ap in enumerate(a)]
           for i, hp in enumerate(h)]
    total = math.fsum(math.fsum(row) for row in raw)
    if not _valid_number(total) or total <= 0:
        raise ValueError("INVALID_SCORE_GRID_MASS")
    grid = tuple(tuple(x / total for x in row) for row in raw)
    if abs(math.fsum(math.fsum(row) for row in grid) - 1) > 1e-12:
        raise ValueError("UNNORMALIZED_SCORE_GRID")
    return grid, {"home_tail_upper_bound": h_tail + 1e-14,
                  "away_tail_upper_bound": a_tail + 1e-14,
                  "combined_tail_upper_bound": h_tail + a_tail + 2e-14}


def one_x_two(grid):
    values = {"HOME": [], "DRAW": [], "AWAY": []}
    for h, row in enumerate(grid):
        for a, mass in enumerate(row):
            values["HOME" if h > a else "DRAW" if h == a else "AWAY"].append(mass)
    return {k: math.fsum(values[k]) for k in THREEWAY}


def three_way_handicap(grid, *, home_handicap):
    """HKJC 3-WAY handicap; handicap DRAW pays, never pushes or half wins."""
    if type(home_handicap) is not int or home_handicap not in (-2, -1, 1, 2):
        raise ValueError("INVALID_THREE_WAY_INTEGER_HANDICAP")
    totals = {"HOME": [], "DRAW": [], "AWAY": []}
    for h, row in enumerate(grid):
        for a, mass in enumerate(row):
            margin = h + home_handicap - a
            totals["HOME" if margin > 0 else "DRAW" if margin == 0
                   else "AWAY"].append(mass)
    return {k: math.fsum(totals[k]) for k in THREEWAY}


def asian_handicap(grid, *, side, line):
    """Asian quarter-lines use the existing canonical 5-grade settlement."""
    if side not in ("HOME", "AWAY"):
        raise ValueError("INVALID_ASIAN_SIDE")
    split_lines(line)
    totals = {key: [] for key in GRADES}
    for h, row in enumerate(grid):
        for a, mass in enumerate(row):
            totals[grade(h, a, side, line)].append(mass)
    return {key: math.fsum(totals[key]) for key in GRADES}


def totals(grid, *, side, line):
    """Same exact score grid -> Asian O/U full, half, push and loss grades."""
    if side not in ("OVER", "UNDER"):
        raise ValueError("INVALID_TOTAL_SIDE")
    legs = split_lines(line)
    if not 0.25 <= float(line) <= 5.0:
        raise ValueError("INVALID_TOTAL_POINT")
    names = {2: "FULL_WIN", 1: "HALF_WIN", 0: "PUSH",
             -1: "HALF_LOSS", -2: "FULL_LOSS"}
    weights = {key: [] for key in GRADES}
    sign = 1 if side == "OVER" else -1
    for h, row in enumerate(grid):
        for a, mass in enumerate(row):
            net = sum(1 if z > 0 else -1 if z < 0 else 0
                      for z in ((4 * (h + a) - leg) * sign for leg in legs))
            weights[names[net]].append(mass)
    return {key: math.fsum(weights[key]) for key in GRADES}


def _rounded(values):
    # All underlying projections use the unrounded matrix; rounding is for
    # display only, so projections do not inherit cross-market rounding drift.
    return {key: round(value, 7) for key, value in values.items()}


def analyze(home_rate, away_rate, *, rho=RHO):
    """One deterministic scenario; explicitly never an authenticated bet."""
    grid, tail = score_grid(home_rate, away_rate, rho=rho)
    p = one_x_two(grid)
    hminus = three_way_handicap(grid, home_handicap=-1)
    hplus = three_way_handicap(grid, home_handicap=1)
    home_ah = asian_handicap(grid, side="HOME", line=-0.75)
    away_ah = asian_handicap(grid, side="AWAY", line=0.75)
    over = totals(grid, side="OVER", line=2.5)
    under = totals(grid, side="UNDER", line=2.5)
    # Independent cross-market algebraic identities check all marginals.
    # Over/Under2.5 cannot push; home-/away+ 0.75 are opposite contracts.
    if (abs(over["FULL_WIN"] + under["FULL_WIN"] - 1) > 1e-12
            or abs(p["HOME"] - (hminus["HOME"] + hminus["DRAW"])) > 1e-12
            or abs(p["AWAY"] - (hplus["DRAW"] + hplus["AWAY"])) > 1e-12
            or any(abs(home_ah[left] - away_ah[right]) > 1e-12
                   for left, right in (("FULL_WIN", "FULL_LOSS"),
                                       ("HALF_WIN", "HALF_LOSS"),
                                       ("PUSH", "PUSH"),
                                       ("HALF_LOSS", "HALF_WIN"),
                                       ("FULL_LOSS", "FULL_WIN")))):
        raise ValueError("CROSS_MARKET_IDENTITY_FAILURE")
    return {
        "schema": "football-king-unified-score-grid-research-v1",
        "model": MODEL if rho == RHO else "rho-zero-numerical-baseline",
        "status": "RESEARCH_ONLY",
        "distribution": "25x25_truncated_poisson_fixed_low_score_DC",
        "source_goal_rates_authentication": False,
        "model_probabilities_calibrated": False,
        "matched_fixture_identity_verified": False,
        "prospective_forecast_seal_verified": False,
        "live_event_or_xg_authenticated": False,
        "half_time_and_next_goal_model_available": False,
        "quoted_bookmaker_market_available": False,
        "verified_positive_ev": False,
        "automated_bets": False,
        "eligible_for_formal_oos_scoring": False,
        "production_recommendations": "DISABLED",
        "input_expected_home_goals_unverified": float(home_rate),
        "input_expected_away_goals_unverified": float(away_rate),
        "fixed_rho": rho,
        "unmodeled_raw_tail_probability_bound": tail["combined_tail_upper_bound"],
        "full_time_1x2": _rounded(p),
        "hkjc_three_way_home_minus_1": _rounded(hminus),
        "hkjc_three_way_home_plus_1": _rounded(hplus),
        "asian_home_minus_0_75": _rounded(home_ah),
        "asian_away_plus_0_75": _rounded(away_ah),
        "total_over_2_5": _rounded(over),
        "total_under_2_5": _rounded(under),
        "probabilities_from_exactly_one_score_grid": True,
        "all_market_internal_consistency_passed": True,
        "notice": ("Pure mathematical research challenger using supplied goal rates. "
                   "Not a verified fixture forecast or offered market price."),
    }
