"""Deterministic joint-scenario portfolio risk diagnostics; paper research only.

Input values are entirely hypothetical. They are NOT independently calibrated
probabilities, real-time bookmaker prices, bankroll instructions or stakes.
Use JOINT outcome vectors to avoid falsely treating same-fixture markets as
independent events. The simulator never chooses, optimizes or recommends an
exposure. No market feeds, user balance or external data are accessed.

A path is an explicit synthetic sequence of scenario indices. Its drawdown
is a *stress example* and NEVER an independently observed backtest.
"""
from math import isfinite, log1p

PRODUCTION_RECOMMENDATIONS = "DISABLED"
MAX_SCENARIOS = 256
MAX_LEGS = 12
MAX_STRESS_PATHS = 64
MAX_STEPS_PER_PATH = 128
MAX_NET_RETURN = 99.0


def _number(value):
    return type(value) in (int, float) and isfinite(value)


def _validate_joint(scenarios, fractions):
    """Validated (probability, per-round P&L) pairs, with no independence."""
    if not isinstance(fractions, (tuple, list)) or not 1 <= len(fractions) <= MAX_LEGS:
        raise ValueError("INVALID_EXPOSURES")
    if any(not _number(f) or f < 0 or f > 1 for f in fractions):
        raise ValueError("INVALID_EXPOSURES")
    if sum(fractions) <= 0 or sum(fractions) > 1.0 + 1e-12:
        raise ValueError("INVALID_TOTAL_EXPOSURE")
    if not isinstance(scenarios, (tuple, list)) or not scenarios:
        raise ValueError("MISSING_JOINT_SCENARIOS")
    if len(scenarios) > MAX_SCENARIOS:
        raise ValueError("TOO_MANY_SCENARIOS")

    joint = []
    for scenario in scenarios:
        if not isinstance(scenario, dict) or set(scenario) != {"probability", "returns"}:
            raise ValueError("INVALID_JOINT_SCENARIO")
        p, returns = scenario["probability"], scenario["returns"]
        if not _number(p) or not 0 <= p <= 1:
            raise ValueError("INVALID_PROBABILITY")
        if not isinstance(returns, (list, tuple)) or len(returns) != len(fractions):
            raise ValueError("MISMATCHED_RETURN_VECTOR")
        if any(not _number(value) or not -1 <= value <= MAX_NET_RETURN
               for value in returns):
            raise ValueError("INVALID_SCENARIO_RETURN")
        # In a simultaneous round, P&L components add; their outcomes
        # are paired within a single joint scenario, NOT independent.
        pnl = sum(f * r for f, r in zip(fractions, returns))
        if not isfinite(pnl) or 1.0 + pnl <= 0:
            raise ValueError("PORTFOLIO_RUIN_SCENARIO")
        joint.append((float(p), pnl))
    if abs(sum(p for p, _ in joint) - 1.0) > 1e-8:
        raise ValueError("JOINT_PROBABILITIES_NOT_NORMALIZED")
    return joint


def _stress_metrics(joint, stress_paths):
    if stress_paths is None:
        stress_paths = ()
    if not isinstance(stress_paths, (list, tuple)):
        raise ValueError("INVALID_STRESS_PATHS")
    if len(stress_paths) > MAX_STRESS_PATHS:
        raise ValueError("TOO_MANY_STRESS_PATHS")
    if not stress_paths:
        return None, None, 0

    # Seed terminal minimum from actual simulated paths, not starting equity.
    # Otherwise every profitable-only stress path incorrectly reports 1.0.
    max_drawdown, worst_terminal = 0.0, float("inf")
    for path in stress_paths:
        if not isinstance(path, (list, tuple)) or not 1 <= len(path) <= MAX_STEPS_PER_PATH:
            raise ValueError("INVALID_STRESS_PATH_LENGTH")
        equity = peak = 1.0
        for index in path:
            if type(index) is not int or not 0 <= index < len(joint):
                raise ValueError("UNKNOWN_STRESS_STATE")
            equity *= 1.0 + joint[index][1]
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, 1.0 - equity / peak)
        worst_terminal = min(worst_terminal, equity)
    return max_drawdown, worst_terminal, len(stress_paths)


def evaluate_hypothetical(joint_scenarios, fractions, stress_paths=None):
    """Study specified fractional exposures; NEVER calculate bet sizing.

    The scenario distribution and stress paths are asserted by the caller,
    not generated from historical matches or inferred from separate bets.
    This is not a certified expected value or recommendation.
    """
    joint = _validate_joint(joint_scenarios, fractions)
    drawdown, terminal, paths = _stress_metrics(joint, stress_paths)
    return {
        "status": "HYPOTHETICAL_ONLY",
        "scenario_count": len(joint),
        "stress_path_count": paths,
        "expected_net_fraction": sum(p * net for p, net in joint),
        "expected_log_growth": sum(p * log1p(net) for p, net in joint),
        "worst_round_net_fraction": min(net for _, net in joint),
        "worst_stress_max_drawdown": drawdown,
        "worst_stress_terminal_equity": terminal,
        "observed_drawdown_verified": False,
        "independent_joint_distribution_verified": False,
        "executable_quote_verified": False,
        "bet_eligible": False,
        "suggested_stake": None,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }


def assess(joint_scenarios=None, fractions=None, stress_paths=None, *,
           hypothetical=False):
    """Fail closed on all unverified real cases regardless of input numbers."""
    held = {
        "status": "HOLD",
        "reason": "NO_VERIFIED_JOINT_DISTRIBUTION_OR_EXECUTABLE_QUOTE",
        "expected_net_fraction": None,
        "expected_log_growth": None,
        "worst_round_net_fraction": None,
        "worst_stress_max_drawdown": None,
        "worst_stress_terminal_equity": None,
        "observed_drawdown_verified": False,
        "independent_joint_distribution_verified": False,
        "executable_quote_verified": False,
        "bet_eligible": False,
        "suggested_stake": None,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
    if hypothetical is not True:
        return held
    return evaluate_hypothetical(joint_scenarios, fractions, stress_paths)
