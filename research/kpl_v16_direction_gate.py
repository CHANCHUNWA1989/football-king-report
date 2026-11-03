"""KPL V16 research-only directional gate and series-clustered calibration checks.

Deliberately does not train/claim an accurate live model. Never derives next-map
strength from a 2:1 series score or from expert votes. Published probabilities
remain unqualified until prospective, point-in-time, out-of-sample validation.
All outputs keep betting HOLD/DISABLED; external data authenticity is unproven.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from functools import lru_cache

from research.kpl_v11_forecast_archive import _time

HISTORY_KEYS = frozenset({
    "series_id", "game_number", "team_a", "team_b", "model_version",
    "model_frozen_at", "forecast_at", "game_start_at", "outcome_observed_at",
    "baseline_captured_at", "model_probability_a", "baseline_probability_a",
    "outcome_a", "held_out", "baseline_source_id"})
CANDIDATE_KEYS = frozenset({
    "series_id", "game_number", "team_a", "team_b", "score_a", "score_b",
    "model_version", "forecast_at", "game_start_at", "info_cutoff_at",
    "phase", "bp_complete", "bp_attested_externally", "probability_a",
    "interval_low_a", "interval_high_a"})


def _id(v):
    return isinstance(v, str) and 0 < len(v) <= 128 and v.strip() == v


def _prob(v):
    return type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1


def bo7_series_probability(score_a, score_b, future_map_probabilities_a):
    """Exact conditional BO7 probability given independently supplied map p's.

    A score alone does NOT imply either side has higher next-map strength.
    """
    if (type(score_a) is not int or type(score_b) is not int or
            min(score_a, score_b) < 0 or max(score_a, score_b) > 4 or
            (score_a == 4 and score_b == 4) or score_a + score_b > 7):
        raise ValueError("invalid BO7 score")
    if not isinstance(future_map_probabilities_a, (list, tuple)):
        raise ValueError("missing map probabilities")
    remaining = 0 if score_a == 4 or score_b == 4 else 7 - score_a - score_b
    if (len(future_map_probabilities_a) != remaining or
            any(not _prob(p) for p in future_map_probabilities_a)):
        raise ValueError("uncalibrated or missing map probabilities")
    @lru_cache(None)
    def walk(a, b, index):
        if a == 4:
            return 1.0
        if b == 4:
            return 0.0
        p = future_map_probabilities_a[index]
        return p * walk(a + 1, b, index + 1) + (1 - p) * walk(a, b + 1, index + 1)
    return walk(score_a, score_b, 0)


def _hold(reasons, *, evaluation=None, conditional_series_prob=None):
    return {
        "status": "HOLD", "research_direction": None,
        "reasons": list(dict.fromkeys(reasons)),
        "evaluation": evaluation,
        "diagnostic_series_probability_a": conditional_series_prob,
        "diagnostic_probability_is_not_next_map_strength": True,
        "independent_source_authentication_verified": False,
        "real_kpl_calibration_verified": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
        "live_execution_allowed": False, "research_only": True}


def evaluate_point_in_time_calibration(history, *, as_of,
                                       min_series=40, min_games=120,
                                       repetitions=700, seed=26):
    """Paired Brier comparison bootstrapped by whole BO series.

    Caller-supplied outcomes/source times are NOT independently authenticated.
    A passing synthetic exercise is a *structural* screening result, not a
    claim of proven KPL calibration or an ability to beat market odds.
    """
    if (not isinstance(history, list) or len(history) > 100_000 or
            type(min_series) is not int or min_series < 2 or
            type(min_games) is not int or min_games < min_series or
            type(repetitions) is not int or not 200 <= repetitions <= 3000):
        raise ValueError("invalid calibration arguments")
    now = _time(as_of)
    groups = defaultdict(list)
    slots, versions, team_orders, frozen_clocks = set(), set(), {}, set()
    for row in history:
        if not isinstance(row, dict) or set(row) != HISTORY_KEYS:
            raise ValueError("invalid calibration row")
        if (not all(_id(row[k]) for k in
                    ("series_id", "team_a", "team_b", "model_version", "baseline_source_id"))
                or row["team_a"] == row["team_b"]
                or type(row["game_number"]) is not int
                or not 1 <= row["game_number"] <= 7
                or type(row["outcome_a"]) is not int
                or row["outcome_a"] not in (0, 1)
                or row["held_out"] is not True
                or not _prob(row["model_probability_a"])
                or not _prob(row["baseline_probability_a"])):
            raise ValueError("invalid/outcome-leaking calibration row")
        t0 = _time(row["model_frozen_at"])
        t1 = _time(row["baseline_captured_at"])
        t2 = _time(row["forecast_at"])
        t3 = _time(row["game_start_at"])
        t4 = _time(row["outcome_observed_at"])
        if not t0 <= t2 < t3 < t4 <= now or not t1 <= t2:
            raise ValueError("future or backfilled history")
        slot = (row["series_id"], row["game_number"])
        if slot in slots:
            raise ValueError("duplicate historic game")
        slots.add(slot)
        pair = (row["team_a"], row["team_b"])
        if row["series_id"] in team_orders and team_orders[row["series_id"]] != pair:
            raise ValueError("team orientation changed within series")
        team_orders[row["series_id"]] = pair
        versions.add(row["model_version"])
        frozen_clocks.add(t0)
        groups[row["series_id"]].append(row)
    if len(versions) != 1 or len(frozen_clocks) != 1:
        raise ValueError("model version/fit must be fixed before historical test")
    n_series, n_games = len(groups), len(history)
    if n_series < min_series or n_games < min_games:
        return {"structural_calibration_gate_passed": False,
                "reasons": ["INSUFFICIENT_INDEPENDENT_SERIES_OR_MAPS"],
                "series_count": n_series, "map_count": n_games,
                "status": "HOLD", "real_kpl_calibration_verified": False}
    per_series = []
    model_brier, baseline_brier, bins = 0.0, 0.0, defaultdict(list)
    for rows in groups.values():
        diffs = []
        for r in rows:
            y, p, b = r["outcome_a"], r["model_probability_a"], r["baseline_probability_a"]
            model_brier += (p - y) ** 2
            baseline_brier += (b - y) ** 2
            diffs.append((b - y) ** 2 - (p - y) ** 2)
            bins[min(int(p * 5), 4)].append((p, y))
        per_series.append((len(diffs), sum(diffs)))
    model_brier /= n_games
    baseline_brier /= n_games
    ece = sum(
        len(group) * abs(sum(p for p, _ in group) / len(group) -
                         sum(y for _, y in group) / len(group))
        for group in bins.values()) / n_games
    rng = random.Random(seed)
    gains = []
    for _ in range(repetitions):
        sample = [per_series[rng.randrange(n_series)] for __ in range(n_series)]
        gains.append(sum(delta for _, delta in sample) /
                     sum(size for size, _ in sample))
    gains.sort()
    lower_95_one_sided = gains[int(0.05 * repetitions)]
    improvement = baseline_brier - model_brier
    reasons = []
    if improvement <= 0 or lower_95_one_sided <= 0:
        reasons.append("NO_SERIES_CLUSTERED_EVIDENCE_OF_BASELINE_GAIN")
    if ece > 0.08:
        reasons.append("CALIBRATION_ERROR_TOO_HIGH_FOR_RESEARCH_GATE")
    return {
        "structural_calibration_gate_passed": not reasons,
        "reasons": reasons or ["HISTORIC_SOURCE_ATTESTATION_NOT_PROVEN_BY_CODE"],
        "series_count": n_series, "map_count": n_games,
        "model_brier": model_brier, "baseline_brier": baseline_brier,
        "paired_brier_gain": improvement,
        "series_cluster_bootstrap_gain_lower_95_one_sided": lower_95_one_sided,
        "ece_5_bins": ece,
        "status": "HOLD", "real_kpl_calibration_verified": False,
        "independent_data_rights_verified": False,
        "production_recommendations": "DISABLED"}


def screen_next_map_direction(candidate, history, *, threshold=0.55,
                              min_series=40, min_games=120):
    """Never turn a tiny p>0.5 into a recommendation.

    Only a narrow, independently evaluated interval beyond a predeclared
    threshold permits a SHADOW research direction. No positive-EV claim.
    """
    if not isinstance(candidate, dict) or set(candidate) != CANDIDATE_KEYS:
        return _hold(["INVALID_CANDIDATE_SCHEMA"])
    try:
        if (not all(_id(candidate[k]) for k in ("series_id", "team_a", "team_b", "model_version"))
                or candidate["team_a"] == candidate["team_b"]
                or type(candidate["game_number"]) is not int
                or type(candidate["score_a"]) is not int
                or type(candidate["score_b"]) is not int
                or candidate["score_a"] + candidate["score_b"] != candidate["game_number"] - 1
                or max(candidate["score_a"], candidate["score_b"]) >= 4
                or candidate["phase"] not in ("PRE_GAME", "BP_LOCKED")
                or not all(_prob(candidate[k]) for k in
                           ("probability_a", "interval_low_a", "interval_high_a"))
                or not candidate["interval_low_a"] <= candidate["probability_a"] <= candidate["interval_high_a"]
                or not 0.5 < threshold < 1):
            return _hold(["INVALID_MAP_CONTEXT_OR_UNCERTAINTY"])
        cutoff, predicted, start = [_time(candidate[k]) for k in
                                    ("info_cutoff_at", "forecast_at", "game_start_at")]
        if not cutoff <= predicted < start:
            return _hold(["CANDIDATE_TIME_LEAKAGE"])
        reasons = []
        if candidate["phase"] != "BP_LOCKED" or candidate["bp_complete"] is not True:
            reasons.append("MISSING_VERIFIED_FOURTH_MAP_BP")
        if candidate["bp_attested_externally"] is not True:
            reasons.append("INDEPENDENT_BP_ATTESTATION_MISSING")
        evaluation = evaluate_point_in_time_calibration(
            history, as_of=candidate["forecast_at"],
            min_series=min_series, min_games=min_games)
        if not evaluation["structural_calibration_gate_passed"]:
            reasons.extend(evaluation["reasons"])
        if evaluation["structural_calibration_gate_passed"]:
            versions = {row["model_version"] for row in history}
            if versions != {candidate["model_version"]}:
                reasons.append("MODEL_VERSION_HAS_NO_MATCHING_HOLDOUT")
        if candidate["interval_low_a"] <= threshold and candidate["interval_high_a"] >= (1 - threshold):
            reasons.append("UNCERTAINTY_INTERVAL_DOES_NOT_SUPPORT_DIRECTION")
        if reasons:
            return _hold(reasons, evaluation=evaluation)
        if candidate["interval_low_a"] > threshold:
            direction = candidate["team_a"]
        elif candidate["interval_high_a"] < 1 - threshold:
            direction = candidate["team_b"]
        else:
            return _hold(["NO_CONSERVATIVE_DIRECTION"], evaluation=evaluation)
        return {
            **_hold(["RESEARCH_SHADOW_ONLY_NOT_AN_EXECUTABLE_PREDICTION"],
                    evaluation=evaluation),
            "research_direction": direction,
            "direction_kind": "SHADOW_ONLY",
        }
    except (ValueError, TypeError, KeyError):
        return _hold(["INVALID_OR_UNVERIFIABLE_FORECAST_INPUT"])
