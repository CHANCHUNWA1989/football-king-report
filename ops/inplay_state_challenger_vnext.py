"""Fixed-coefficient in-play 1X2/comeback *research* challenger.

Offline, zero network: requires PR-02's RESEARCH_ONLY consensus and
separately claimed frozen pre-match rates. Neither the source nor the
prediction clock is independently authenticated. NO certified model
calibration, trading price, EV, or recommendation is produced.
"""
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone

from score_distribution_vnext import one_x_two, validate_matrix

SCHEMA = "football-king-vnext-inplay-comeback-challenger-v1"
MODEL_ID = "inplay-fixed-score-state-v1-uncalibrated"
MAX_SCORE = 10
MAX_REDS = 3
MAX_EXTRA_GOALS = 65
FIXED_SCORE_COEFFICIENT = .075
FIXED_RED_COEFFICIENT = .20


def _clock(value):
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("NAIVE_TIMESTAMP")
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc


def _valid_id(v):
    return type(v) is str and 1 <= len(v) <= 128 and v.strip() == v and v.isprintable()


def _valid_digest(v):
    return (type(v) is str and len(v) == 64
            and all(ch in "0123456789abcdef" for ch in v))


def _rate(v):
    if type(v) not in (int, float) or not math.isfinite(v) or not .1 <= v <= 5.5:
        raise ValueError("INVALID_PREMATCH_RATE")
    return float(v)


def _poisson(mean):
    if not math.isfinite(mean) or mean < 0 or mean > 24:
        raise ValueError("INVALID_REMAINING_RATE")
    if mean == 0:
        return (1.0,)
    terms = [math.exp(-mean)]
    for i in range(1, MAX_EXTRA_GOALS + 1):
        if 1.0 - math.fsum(terms) <= 1e-12:
            break
        terms.append(terms[-1] * mean / i)
    if 1.0 - math.fsum(terms) > 1e-12:
        raise ValueError("EXCESSIVE_TAIL_MASS")
    return tuple(terms)


def _prematch(pre, *, fixture_id, kickoff):
    if type(pre) is not dict or set(pre) != {
        "fixture_id", "model_id", "forecast_utc", "inputs_available_utc",
        "expected_home_goals", "expected_away_goals", "input_sha256",
        "production_recommendations", "calibrated"
    }:
        raise ValueError("INVALID_PREMATCH_ARCHIVE_SCHEMA")
    if (pre["fixture_id"] != fixture_id or not _valid_id(pre["model_id"])
            or pre["production_recommendations"] != "DISABLED"
            or pre["calibrated"] is not False
            or not _valid_digest(pre["input_sha256"])):
        raise ValueError("INVALID_PREMATCH_ARCHIVE")
    forecast, available = _clock(pre["forecast_utc"]), _clock(pre["inputs_available_utc"])
    if not available <= forecast <= kickoff - timedelta(minutes=10):
        raise ValueError("PREMATCH_LOOKAHEAD_OR_UNSEALED")
    return _rate(pre["expected_home_goals"]), _rate(pre["expected_away_goals"])


def _consensus(proof, *, fixture_id, decision, home, away, red_home, red_away):
    if type(proof) is not dict or proof.get("status") != "RESEARCH_ONLY":
        raise ValueError("MISSING_RESEARCH_EVENT_CONSENSUS")
    if (proof.get("fixture_id") != fixture_id
            or _clock(proof.get("decision_utc")) != decision
            or proof.get("score_home") != home or proof.get("score_away") != away
            or proof.get("active_red_cards") != {"HOME": red_home, "AWAY": red_away}
            or proof.get("production_recommendations") != "DISABLED"
            or proof.get("model_scoring_eligible") is not False
            or proof.get("source_authenticated") is not False
            or proof.get("source_independence_verified") is not False
            or not _valid_digest(proof.get("evidence_input_sha256"))):
        raise ValueError("CONFLICTING_OR_UNTRUSTED_CONSENSUS")
    # A passing proof remains a structural research assertion only.
    return proof["evidence_input_sha256"]


def remaining_matrix(home_mean, away_mean, home_goals, away_goals):
    """Shift remaining-goal Poisson mass onto full-time 90-minute scorelines."""
    if (type(home_goals) is not int or type(away_goals) is not int
            or not 0 <= home_goals <= MAX_SCORE or not 0 <= away_goals <= MAX_SCORE):
        raise ValueError("INVALID_CURRENT_SCORE")
    left, right = _poisson(home_mean), _poisson(away_mean)
    height, width = home_goals + len(left), away_goals + len(right)
    if height > 81 or width > 81:
        raise ValueError("SCORE_GRID_TOO_LARGE")
    grid = [[0.0] * width for _ in range(height)]
    for i, hp in enumerate(left):
        for j, ap in enumerate(right):
            grid[home_goals + i][away_goals + j] = hp * ap
    mass = math.fsum(p for row in grid for p in row)
    if mass <= 0 or not math.isfinite(mass):
        raise ValueError("BAD_REMAINING_MASS")
    result = tuple(tuple(p / mass for p in row) for row in grid)
    validate_matrix(result)
    return result


def predict(snapshot):
    """Research-only dynamic probability from claimed as-of match observations.

    Fixed coefficients are illustrative, not fitted. Stoppage time, extra time,
    second yellow event normalization and time-varying future tactics are NOT
    learned. In-play minute >=90 is withheld rather than pretending certainty.
    """
    if type(snapshot) is not dict or set(snapshot) != {
        "fixture_id", "kickoff_utc", "decision_utc", "minute_elapsed",
        "score_home", "score_away", "red_home", "red_away",
        "prematch", "event_consensus"
    }:
        raise ValueError("INVALID_INPLAY_SNAPSHOT_SCHEMA")
    fid = snapshot["fixture_id"]
    if not _valid_id(fid):
        raise ValueError("INVALID_FIXTURE_ID")
    kickoff, decision = _clock(snapshot["kickoff_utc"]), _clock(snapshot["decision_utc"])
    minute = snapshot["minute_elapsed"]
    if type(minute) is not int or not 0 <= minute < 90:
        raise ValueError("UNSUPPORTED_INPLAY_MINUTE_OR_STOPPAGE")
    elapsed_wall = (decision - kickoff).total_seconds() / 60
    if not minute <= elapsed_wall + 3 or not elapsed_wall - minute <= 20:
        raise ValueError("IMPOSSIBLE_OR_STALE_MATCH_CLOCK")
    home, away, red_home, red_away = [snapshot[k] for k in (
        "score_home", "score_away", "red_home", "red_away")]
    if (any(type(k) is not int for k in (home, away, red_home, red_away))
            or not 0 <= home <= MAX_SCORE or not 0 <= away <= MAX_SCORE
            or not 0 <= red_home <= MAX_REDS or not 0 <= red_away <= MAX_REDS):
        raise ValueError("INVALID_SCORE_OR_RED_CARDS")
    base_h, base_a = _prematch(snapshot["prematch"], fixture_id=fid, kickoff=kickoff)
    evidence_sha = _consensus(snapshot["event_consensus"], fixture_id=fid,
                              decision=decision, home=home, away=away,
                              red_home=red_home, red_away=red_away)
    remainder = (90 - minute) / 90.0
    score_gap = max(-4, min(4, home - away))
    red_gap = red_away - red_home
    h = base_h * remainder * math.exp(-FIXED_SCORE_COEFFICIENT * score_gap
                                       + FIXED_RED_COEFFICIENT * red_gap)
    a = base_a * remainder * math.exp(FIXED_SCORE_COEFFICIENT * score_gap
                                       - FIXED_RED_COEFFICIENT * red_gap)
    matrix = remaining_matrix(h, a, home, away)
    probabilities = one_x_two(matrix)
    trailing = "HOME" if home < away else "AWAY" if away < home else None
    top = sorted(((prob, i, j) for i, row in enumerate(matrix)
                  for j, prob in enumerate(row)), reverse=True)[:5]
    return {
        "schema": SCHEMA, "status": "RESEARCH_ONLY", "model_id": MODEL_ID,
        "fixture_id": fid, "decision_utc": decision.isoformat(),
        "minute_elapsed": minute, "current_score": [home, away],
        "input_evidence_sha256_unattested": evidence_sha,
        "prematch_input_sha256_unattested": snapshot["prematch"]["input_sha256"],
        "remaining_expected_home_goals": h, "remaining_expected_away_goals": a,
        "fulltime_probabilities": probabilities,
        "trailing_team": trailing,
        "trailing_team_comeback_win_probability": (
            probabilities[trailing] if trailing else None),
        "top_fulltime_scores": [
            {"home": x, "away": y, "probability": prob}
            for prob, x, y in top],
        "fixed_coefficients_not_trained": True,
        "stoppage_time_not_modelled": True,
        "independent_clock_attestation": False,
        "source_authenticated": False,
        "model_calibrated": False,
        "model_scoring_eligible": False,
        "positive_ev_verified": False,
        "betting_recommendation_allowed": False,
        "production_recommendations": "DISABLED",
    }


def audit_predict(snapshot):
    try:
        return predict(snapshot)
    except (TypeError, KeyError, ValueError, OverflowError) as exc:
        return {
            "schema": SCHEMA, "status": "HOLD",
            "reason": str(exc) or "INVALID_INPUT",
            "source_authenticated": False, "model_calibrated": False,
            "model_scoring_eligible": False, "positive_ev_verified": False,
            "betting_recommendation_allowed": False,
            "production_recommendations": "DISABLED",
        }
