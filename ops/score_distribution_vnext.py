"""Unified regulation-90-minute score and market *research* distribution.

Offline mathematical sidecar. A shared score matrix drives 1X2, Asian
handicap and totals: no re-fitting by market, no sportsbook odds or EV.
Expected-goal inputs and source provenance are NOT independently verified.
Research-only outputs always preserve production DISABLED.
"""
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math

from asian_handicap_research import quarter_units as legacy_handicap_units

SCHEMA = "football-king-unified-score-markets-vnext-v1"
GRADE_NAMES = ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")
MAX_GRID = 80
MAX_MARKETS = 24
MAX_TAIL = 1e-8
MIN_TAIL = 1e-13
MODEL = "independent-poisson-with-optional-fixed-dc-correction-research"


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _rate(value):
    if not _number(value) or not .1 <= value <= 5.5:
        raise ValueError("INVALID_EXPECTED_GOALS")
    return float(value)


def _poisson_terms(rate, tolerance):
    terms = [math.exp(-rate)]
    # Bound truncation independently on each marginal to control joint tail.
    for index in range(1, MAX_GRID + 1):
        if 1.0 - math.fsum(terms) <= tolerance:
            break
        terms.append(terms[-1] * rate / index)
    if 1.0 - math.fsum(terms) > tolerance:
        raise ValueError("POISSON_TAIL_NOT_BOUNDED")
    return terms


def score_matrix(home_rate, away_rate, *, rho=0.0, tail_tolerance=1e-10):
    """One normalized finite PMF; optional fixed Dixon-Coles low-score rho.

    Not a fitted or prospective calibration. No actual match observations,
    price or post-match result is accepted by this API.
    """
    h, a = _rate(home_rate), _rate(away_rate)
    if not _number(rho) or not -.15 <= rho <= .10:
        raise ValueError("INVALID_FIXED_RHO")
    if (not _number(tail_tolerance) or not MIN_TAIL <= tail_tolerance <= MAX_TAIL):
        raise ValueError("INVALID_TAIL_TOLERANCE")
    tau = {
        (0, 0): 1.0 - h * a * rho,
        (0, 1): 1.0 + h * rho,
        (1, 0): 1.0 + a * rho,
        (1, 1): 1.0 - rho,
    }
    if any(not math.isfinite(v) or v <= 0 for v in tau.values()):
        raise ValueError("NONPOSITIVE_DIXON_COLES_FACTOR")
    ph = _poisson_terms(h, tail_tolerance / 4.0)
    pa = _poisson_terms(a, tail_tolerance / 4.0)
    raw = tuple(tuple(x * y * tau.get((i, j), 1.0)
                      for j, y in enumerate(pa)) for i, x in enumerate(ph))
    mass = math.fsum(v for row in raw for v in row)
    if not math.isfinite(mass) or mass <= 0:
        raise ValueError("INVALID_SCORE_MASS")
    grid = tuple(tuple(v / mass for v in row) for row in raw)
    validate_matrix(grid)
    return grid


def validate_matrix(matrix):
    """Validate a supplied finite, already normalized score PMF; never fix it."""
    if type(matrix) not in (tuple, list) or not 1 <= len(matrix) <= MAX_GRID + 1:
        raise ValueError("INVALID_MATRIX_SHAPE")
    width = None
    for row in matrix:
        if type(row) not in (tuple, list) or not 1 <= len(row) <= MAX_GRID + 1:
            raise ValueError("INVALID_MATRIX_SHAPE")
        if width is None:
            width = len(row)
        if len(row) != width:
            raise ValueError("RAGGED_MATRIX")
        if any(not _number(p) or p < 0 or p > 1 for p in row):
            raise ValueError("INVALID_MATRIX_PROBABILITY")
    total = math.fsum(p for row in matrix for p in row)
    if abs(total - 1.0) > 1e-9:
        raise ValueError("MATRIX_NOT_NORMALIZED")
    return matrix


def _units(line, *, market):
    if isinstance(line, bool) or not isinstance(line, (int, float, str, Decimal)):
        raise ValueError("INVALID_MARKET_LINE")
    try:
        value = Decimal(str(line))
    except InvalidOperation as exc:
        raise ValueError("INVALID_MARKET_LINE") from exc
    if not value.is_finite():
        raise ValueError("INVALID_MARKET_LINE")
    if market == "asian_handicap":
        # Reuse and match the strict existing quarter-line validator and range.
        return legacy_handicap_units(line)
    if market != "totals" or not 0 <= value <= 20:
        raise ValueError("TOTAL_LINE_OUT_OF_RESEARCH_RANGE")
    quarters = value * 4
    if quarters != quarters.to_integral_value():
        raise ValueError("NOT_A_QUARTER_GOAL")
    return int(quarters)


def _halves(units):
    return (units, units) if units % 2 == 0 else (units - 1, units + 1)


def _five_grade(leg_a, leg_b):
    net = (1 if leg_a > 0 else -1 if leg_a < 0 else 0)
    net += (1 if leg_b > 0 else -1 if leg_b < 0 else 0)
    return {2: "FULL_WIN", 1: "HALF_WIN", 0: "PUSH",
            -1: "HALF_LOSS", -2: "FULL_LOSS"}[net]


def grade_score(home_goals, away_goals, *, market, side, line=None):
    """Grade one regulation FT score; Asian line belongs to selected side.

    A minus handicap means that team gives goals. Totals are full-match goals.
    Excludes extra-time, penalties and 'remaining match only' in-play markets.
    """
    if (type(home_goals) is not int or type(away_goals) is not int
            or not 0 <= home_goals <= MAX_GRID or not 0 <= away_goals <= MAX_GRID):
        raise ValueError("INVALID_FINAL_SCORE")
    if market == "h2h":
        if line is not None or side not in ("HOME", "DRAW", "AWAY"):
            raise ValueError("INVALID_1X2_MARKET")
        winner = "HOME" if home_goals > away_goals else "AWAY" if home_goals < away_goals else "DRAW"
        return "WIN" if winner == side else "LOSS"
    if market == "asian_handicap":
        if side not in ("HOME", "AWAY"):
            raise ValueError("INVALID_HANDICAP_SIDE")
        quarter = _units(line, market=market)
        margin = home_goals - away_goals if side == "HOME" else away_goals - home_goals
        first, second = _halves(quarter)
        return _five_grade(4 * margin + first, 4 * margin + second)
    if market == "totals":
        if side not in ("OVER", "UNDER"):
            raise ValueError("INVALID_TOTAL_SIDE")
        first, second = _halves(_units(line, market=market))
        total = 4 * (home_goals + away_goals)
        direction = 1 if side == "OVER" else -1
        return _five_grade(direction * (total - first),
                           direction * (total - second))
    raise ValueError("UNSUPPORTED_MARKET")


def one_x_two(matrix):
    validate_matrix(matrix)
    return {
        "HOME": math.fsum(p for i, row in enumerate(matrix) for j, p in enumerate(row) if i > j),
        "DRAW": math.fsum(p for i, row in enumerate(matrix) for j, p in enumerate(row) if i == j),
        "AWAY": math.fsum(p for i, row in enumerate(matrix) for j, p in enumerate(row) if i < j),
    }


def market_distribution(matrix, *, market, side, line=None):
    """Use EXACTLY the given PMF for all market grade probabilities."""
    validate_matrix(matrix)
    if market == "h2h":
        if side not in ("HOME", "DRAW", "AWAY") or line is not None:
            raise ValueError("INVALID_1X2_MARKET")
        return {"market": "h2h", "side": side, "line": None,
                "outcome_probabilities": one_x_two(matrix),
                "selected_probability": one_x_two(matrix)[side]}
    # Validate market/side/line before iterating any scorelines.
    grade_score(0, 0, market=market, side=side, line=line)
    values = {name: 0.0 for name in GRADE_NAMES}
    buckets = {name: [] for name in GRADE_NAMES}
    for h, row in enumerate(matrix):
        for a, probability in enumerate(row):
            label = grade_score(h, a, market=market, side=side, line=line)
            buckets[label].append(probability)
    for name in GRADE_NAMES:
        values[name] = math.fsum(buckets[name])
    if abs(math.fsum(values.values()) - 1.0) > 1e-9:
        raise ValueError("MARKET_PROBABILITIES_INVALID")
    return {
        "market": market, "side": side,
        "line": float(Decimal(str(line))),
        "outcome_probabilities": values,
        "actual_market_quote_verified": False,
        "positive_ev_verified": False,
    }


def _stamp(matrix):
    payload = json.dumps(matrix, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def build_report(home_rate, away_rate, markets, *, rho=0.0):
    """Atomic research report: invalid selection rejects whole batch."""
    if type(markets) not in (tuple, list) or not 1 <= len(markets) <= MAX_MARKETS:
        raise ValueError("INVALID_MARKET_REQUESTS")
    grid = score_matrix(home_rate, away_rate, rho=rho)
    seen, scenarios = set(), []
    for request in markets:
        if type(request) is not dict or set(request) != {"market", "side", "line"}:
            raise ValueError("INVALID_MARKET_REQUEST")
        market, side, line = (request[k] for k in ("market", "side", "line"))
        key = (market, side, None if market == "h2h" else _units(line, market=market))
        if key in seen:
            raise ValueError("DUPLICATE_MARKET_REQUEST")
        seen.add(key)
        scenarios.append(market_distribution(grid, market=market, side=side, line=line))
    outcome = one_x_two(grid)
    top = sorted(((p, h, a) for h, row in enumerate(grid)
                  for a, p in enumerate(row)), reverse=True)[:8]
    return {
        "schema": SCHEMA, "status": "RESEARCH_ONLY", "model_id": MODEL,
        "full_time_scope": "REGULATION_90_MINUTES_INCLUDING_STOPPAGE",
        "remaining_only_in_play_markets_supported": False,
        "home_expected_goals": float(home_rate), "away_expected_goals": float(away_rate),
        "fixed_rho": float(rho), "score_matrix_sha256": _stamp(grid),
        "matrix_dimensions": [len(grid), len(grid[0])],
        "probabilities_1x2": outcome,
        "top_scorelines": [{"home": h, "away": a, "probability": p} for p, h, a in top],
        "markets": scenarios,
        "input_point_in_time_verified": False,
        "model_calibrated": False, "source_authenticated": False,
        "bookmaker_quote_authenticated": False, "positive_ev_verified": False,
        "qualifies_for_betting": False, "model_scoring_eligible": False,
        "production_recommendations": "DISABLED",
    }


def audit_report(home_rate, away_rate, markets, *, rho=0.0):
    """Fail closed on any invalid model input, line or market selection."""
    try:
        return build_report(home_rate, away_rate, markets, rho=rho)
    except (ValueError, TypeError, OverflowError, InvalidOperation) as exc:
        return {
            "schema": SCHEMA, "status": "HOLD", "reason": str(exc) or "INVALID_INPUT",
            "input_point_in_time_verified": False, "model_calibrated": False,
            "bookmaker_quote_authenticated": False, "positive_ev_verified": False,
            "qualifies_for_betting": False, "model_scoring_eligible": False,
            "production_recommendations": "DISABLED",
        }
