"""Synthetic, non-calibrated lineup replacement sensitivity, never a forecast.

No injury reports, real player ratings, source authentication or betting output.
All coefficients are predeclared illustrative stress parameters, not estimates.
"""
import math
from itertools import combinations

MODEL_ID = "availability-synthetic-sensitivity-v1"
# Separate attack/defense channel weights; intentionally illustrative.
ROLE_WEIGHTS = {"GK": (0.02, 0.24), "DEF": (0.07, 0.18),
                "MID": (0.14, 0.11), "FWD": (0.22, 0.05)}
INTERACTION = 0.08
MAX_LOG_EFFECT = 0.7


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def number(x, low, high):
    return type(x) in (int, float) and math.isfinite(x) and low <= x <= high


def rating(x):
    require(type(x) is list and len(x) == 2 and all(number(v, 0, 1) for v in x),
            "INVALID_SYNTHETIC_RATING")
    return x


def identifier(x, seen):
    require(type(x) is str and 1 <= len(x) <= 80 and x == x.strip()
            and all(c.isascii() and (c.isalnum() or c in "-_") for c in x),
            "INVALID_SYNTHETIC_ID")
    require(x not in seen, "DUPLICATE_PLAYER_ID")
    seen.add(x)


def team(slots, seen):
    require(type(slots) is list and len(slots) == 11, "INCOMPLETE_XI")
    losses = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    count = 0
    for slot in slots:
        require(type(slot) is dict and set(slot) ==
                {"starter_id", "replacement_id", "role", "starter", "replacement"},
                "INVALID_SLOT_FIELDS")
        role = slot["role"]
        require(type(role) is str and role in ROLE_WEIGHTS, "INVALID_ROLE")
        identifier(slot["starter_id"], seen)
        starter = rating(slot["starter"])
        replacement_id, replacement = slot["replacement_id"], slot["replacement"]
        require((replacement_id is None) == (replacement is None),
                "INCOMPLETE_REPLACEMENT")
        if replacement_id is None:
            losses[role].append((0.0, 0.0))
        else:
            identifier(replacement_id, seen)
            repl = rating(replacement)
            count += 1
            losses[role].append(tuple(a-b for a, b in zip(starter, repl)))
    require(len(losses["GK"]) == 1 and all(losses[r] for r in ROLE_WEIGHTS),
            "INVALID_ROLE_COVERAGE")
    linear, interaction = [0.0, 0.0], [0.0, 0.0]
    for role, gaps in losses.items():
        for c in range(2):
            linear[c] += ROLE_WEIGHTS[role][c] * sum(g[c] for g in gaps)
            interaction[c] += INTERACTION * sum(max(0, a[c])*max(0, b[c])
                                                 for a, b in combinations(gaps, 2))
    raw = [a+b for a, b in zip(linear, interaction)]
    bounded = [max(-MAX_LOG_EFFECT, min(MAX_LOG_EFFECT, x)) for x in raw]
    return {"replacement_count": count, "attack_linear": linear[0],
            "defense_linear": linear[1], "attack_interaction": interaction[0],
            "defense_interaction": interaction[1], "attack_log_loss": bounded[0],
            "defense_log_loss": bounded[1], "effect_capped": raw != bounded}


def evaluate(scenario):
    """Return illustrative adjusted rates only for an explicit synthetic XI."""
    require(type(scenario) is dict and set(scenario) ==
            {"kind", "home_xg", "away_xg", "home", "away"}, "INVALID_SCENARIO_FIELDS")
    require(scenario["kind"] == "SYNTHETIC_SCENARIO_ONLY", "REAL_INPUT_NOT_SUPPORTED")
    h, a = scenario["home_xg"], scenario["away_xg"]
    require(number(h, 0.05, 5.0) and number(a, 0.05, 5.0), "INVALID_BASE_RATE")
    seen = set()
    home, away = team(scenario["home"], seen), team(scenario["away"], seen)
    h_new = h * math.exp(-home["attack_log_loss"] + away["defense_log_loss"])
    a_new = a * math.exp(-away["attack_log_loss"] + home["defense_log_loss"])
    return {"model_id": MODEL_ID, "status": "SYNTHETIC_RESEARCH_ONLY",
            "scenario_xg": {"home": h_new, "away": a_new},
            "home_effect": home, "away_effect": away,
            "coefficients_calibrated": False, "real_player_effect_verified": False,
            "actual_xg_verified": False, "official_lineup_authenticated": False,
            "certified_forward_samples": 0, "ev": None,
            "production_recommendations": "DISABLED"}
