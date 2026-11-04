"""Single-matrix, pre-match football market math (offline RESEARCH ONLY).

One bounded Poisson joint score matrix is reused to derive 1X2, full-time
Asian handicap and full-time Asian totals. Every market is hypothetical.
No quotes, odds, EV, bets, live prediction or provider authentication.
"""
import hashlib
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from point_in_time_store import verify_pinned_cut

SCHEMA = "football-king-unified-score-distribution-vnext-v1"
GRADES = ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")
GRADE_BY_SUM = {2: "FULL_WIN", 1: "HALF_WIN", 0: "PUSH",
                -1: "HALF_LOSS", -2: "FULL_LOSS"}
MAX_RATE = 5.5
MAX_GRID_SIDE = 65
TAIL_TOL = 1e-10
MASS_TOL = 1e-9
FORECAST_KEYS = frozenset((
    "fixture_id", "model_id", "forecast_utc", "kickoff_utc",
    "expected_home_goals", "expected_away_goals", "cut_input_sha256",
    "production_recommendations",
))


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _time(value):
    if type(value) is not str:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("NAIVE_TIMESTAMP")
        return instant.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc


def _sha(obj):
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _poisson(rate):
    if not _finite(rate) or not 0 <= rate <= MAX_RATE:
        raise ValueError("INVALID_EXPECTED_GOALS")
    term = math.exp(-rate)
    probs = [term]
    for k in range(1, MAX_GRID_SIDE):
        if 1 - math.fsum(probs) <= TAIL_TOL / 4:
            break
        term *= rate / k
        probs.append(term)
    mass = math.fsum(probs)
    tail = max(0.0, 1.0 - mass)
    if tail > TAIL_TOL / 4 + 1e-15 or mass <= 0:
        raise ValueError("UNBOUNDED_POISSON_TAIL")
    return [p / mass for p in probs], tail


def score_matrix(expected_home_goals, expected_away_goals):
    """Normalized two-dimensional probability grid plus truncation bound."""
    home, tail_home = _poisson(expected_home_goals)
    away, tail_away = _poisson(expected_away_goals)
    matrix = [[h * a for a in away] for h in home]
    mass = math.fsum(v for row in matrix for v in row)
    matrix = [[v / mass for v in row] for row in matrix]
    validate_matrix(matrix)
    return {"matrix": matrix, "tail_mass_upper_bound": min(1.0, tail_home + tail_away)}


def validate_matrix(matrix):
    if (type(matrix) is not list or not 1 <= len(matrix) <= MAX_GRID_SIDE
            or type(matrix[0]) is not list
            or not 1 <= len(matrix[0]) <= MAX_GRID_SIDE):
        raise ValueError("INVALID_SCORE_MATRIX_SHAPE")
    width = len(matrix[0])
    values = []
    for row in matrix:
        if type(row) is not list or len(row) != width:
            raise ValueError("RAGGED_SCORE_MATRIX")
        if any(not _finite(value) or value < 0 for value in row):
            raise ValueError("NONFINITE_OR_NEGATIVE_MATRIX_PROBABILITY")
        values.extend(row)
    if abs(math.fsum(values) - 1) > MASS_TOL:
        raise ValueError("SCORE_MATRIX_NOT_NORMALIZED")
    return matrix


def _score(home_goals, away_goals):
    if (type(home_goals) is not int or type(away_goals) is not int
            or min(home_goals, away_goals) < 0
            or max(home_goals, away_goals) > MAX_GRID_SIDE):
        raise ValueError("INVALID_FINAL_GOALS")


def quarter_units(line, *, minimum, maximum):
    """Exact quarter-goal parser: never silently round unsupported lines."""
    if isinstance(line, bool) or not isinstance(line, (int, float, str, Decimal)):
        raise ValueError("INVALID_MARKET_LINE")
    try:
        value = Decimal(str(line))
    except InvalidOperation as exc:
        raise ValueError("INVALID_MARKET_LINE") from exc
    if not value.is_finite() or not Decimal(str(minimum)) <= value <= Decimal(str(maximum)):
        raise ValueError("MARKET_LINE_OUT_OF_RANGE")
    units = 4 * value
    if units != units.to_integral_value():
        raise ValueError("NOT_QUARTER_GOAL_LINE")
    return int(units)


def _legs(units):
    return (units, units) if units % 2 == 0 else (units - 1, units + 1)


def _grade(value1, value2):
    def sign(value):
        return (value > 0) - (value < 0)
    return GRADE_BY_SUM[sign(value1) + sign(value2)]


def grade_asian_handicap(home_goals, away_goals, *, side, line):
    """Line applies to the selected HOME/AWAY side, at FT inclusive of all goals."""
    _score(home_goals, away_goals)
    if side not in ("HOME", "AWAY"):
        raise ValueError("INVALID_HANDICAP_SIDE")
    units = quarter_units(line, minimum=-10, maximum=10)
    delta = home_goals - away_goals if side == "HOME" else away_goals - home_goals
    low, high = _legs(units)
    return _grade(4 * delta + low, 4 * delta + high)


def grade_asian_total(home_goals, away_goals, *, side, line):
    """FT OVER/UNDER goal market, not 'remaining match' in-play totals."""
    _score(home_goals, away_goals)
    if side not in ("OVER", "UNDER"):
        raise ValueError("INVALID_TOTAL_SIDE")
    units = quarter_units(line, minimum=0, maximum=20)
    low, high = _legs(units)
    total = 4 * (home_goals + away_goals)
    factor = 1 if side == "OVER" else -1
    return _grade(factor * (total - low), factor * (total - high))


def win_draw_loss(matrix):
    validate_matrix(matrix)
    return {
        "HOME": math.fsum(p for h, row in enumerate(matrix)
                          for a, p in enumerate(row) if h > a),
        "DRAW": math.fsum(p for h, row in enumerate(matrix)
                          for a, p in enumerate(row) if h == a),
        "AWAY": math.fsum(p for h, row in enumerate(matrix)
                          for a, p in enumerate(row) if h < a),
    }


def market_grades(matrix, *, market, side, line):
    validate_matrix(matrix)
    if market == "ASIAN_HANDICAP":
        if side not in ("HOME", "AWAY"):
            raise ValueError("INVALID_HANDICAP_SIDE")
        quarter_units(line, minimum=-10, maximum=10)
        grade = grade_asian_handicap
    elif market == "ASIAN_TOTAL":
        if side not in ("OVER", "UNDER"):
            raise ValueError("INVALID_TOTAL_SIDE")
        quarter_units(line, minimum=0, maximum=20)
        grade = grade_asian_total
    else:
        raise ValueError("UNSUPPORTED_MARKET")
    buckets = {label: [] for label in GRADES}
    for h, row in enumerate(matrix):
        for a, p in enumerate(row):
            buckets[grade(h, a, side=side, line=line)].append(p)
    return {key: math.fsum(buckets[key]) for key in GRADES}


def _hold(reason):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "research_only": True, "source_authenticated": False,
        "input_clock_externally_attested": False,
        "model_calibrated": False, "bookmaker_quote_authenticated": False,
        "positive_ev_verified": False, "model_scoring_eligible": False,
        "production_recommendations": "DISABLED", "recommended_bets": [],
    }


def research_prematch(forecast, pit_cut, *, externally_pinned_cut_sha256,
                      handicap_side, handicap_line, total_side, total_line):
    """Produce a single-score-matrix hypothetical research report.

    The caller MUST obtain the pinned digest from separately trusted storage;
    supplying the cut's own digest as its 'external' pin proves nothing.
    No authentication or model qualification is certified by this routine.
    """
    try:
        if type(forecast) is not dict or set(forecast) != FORECAST_KEYS:
            raise ValueError("INVALID_FORECAST_SCHEMA")
        if (forecast["production_recommendations"] != "DISABLED"
                or type(forecast["fixture_id"]) is not str
                or not forecast["fixture_id"].strip()
                or type(forecast["model_id"]) is not str
                or not forecast["model_id"].strip()):
            raise ValueError("UNSAFE_FORECAST_IDENTITY")
        if not isinstance(pit_cut, dict) or pit_cut.get("phase") != "PREMATCH":
            raise ValueError("ONLY_PREMATCH_CUTS_SUPPORTED")
        if not verify_pinned_cut(pit_cut, externally_pinned_cut_sha256):
            raise ValueError("MISSING_OR_UNPINNED_EVIDENCE_CUT")
        if (pit_cut.get("fixture_id") != forecast["fixture_id"]
                or forecast["cut_input_sha256"] != pit_cut["input_sha256"]
                or pit_cut.get("source_authenticated") is not False
                or pit_cut.get("external_clock_attested") is not False):
            raise ValueError("EVIDENCE_CUT_IDENTITY_OR_TRUST_CONFLICT")
        cutoff = _time(pit_cut["decision_utc"])
        predicted = _time(forecast["forecast_utc"])
        kickoff = _time(forecast["kickoff_utc"])
        if not cutoff <= predicted < kickoff:
            raise ValueError("FORECAST_NOT_POINT_IN_TIME_PREMATCH")
        grid = score_matrix(forecast["expected_home_goals"], forecast["expected_away_goals"])
        matrix = grid["matrix"]
        h2h = win_draw_loss(matrix)
        ah = market_grades(matrix, market="ASIAN_HANDICAP", side=handicap_side,
                           line=handicap_line)
        ou = market_grades(matrix, market="ASIAN_TOTAL", side=total_side,
                           line=total_line)
        if (abs(math.fsum(h2h.values()) - 1) > MASS_TOL
                or abs(math.fsum(ah.values()) - 1) > MASS_TOL
                or abs(math.fsum(ou.values()) - 1) > MASS_TOL):
            raise ValueError("INCONSISTENT_MARKET_DISTRIBUTIONS")
        return {
            **_hold("HYPOTHETICAL_MATH_ONLY_NOT_VERIFIED_VALUE"),
            "status": "RESEARCH_ONLY",
            "fixture_id": forecast["fixture_id"], "model_id": forecast["model_id"],
            "forecast_utc": predicted.isoformat(),
            "evidence_input_sha256": pit_cut["input_sha256"],
            "matrix_sha256": _sha(matrix),
            "score_matrix": matrix,
            "matrix_rows": len(matrix), "matrix_cols": len(matrix[0]),
            "tail_mass_upper_bound": grid["tail_mass_upper_bound"],
            "markets": {
                "h2h": h2h,
                "asian_handicap": {
                    "side": handicap_side, "hypothetical_line": str(handicap_line),
                    "grades": ah,
                },
                "asian_total": {
                    "side": total_side, "hypothetical_line": str(total_line),
                    "grades": ou,
                },
            },
            "line_settlement_basis": "FULL_TIME_90_MINUTES",
            "point_in_time_metadata_not_independent_proof": True,
        }
    except (TypeError, KeyError, ValueError, OverflowError, AttributeError) as exc:
        return _hold(str(exc) or "INVALID_RESEARCH_INPUT")
