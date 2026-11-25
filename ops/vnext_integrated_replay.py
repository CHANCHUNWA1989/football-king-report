"""Offline VNext research replay. No authenticated data, EV or release."""
import math
from live_snapshot_commitment import audit_bound_predict
from live_snapshot_adapter import hold
from inplay_state_challenger_vnext import remaining_matrix
from score_distribution_vnext import one_x_two, market_distribution


class ReplayDistributionError(ValueError):
    """The replay probabilities disagree with the challenger or lose mass."""


def replay_distributions(model, markets):
    """Grade all requested lines using the challenger's full-time score matrix."""
    grid = remaining_matrix(model["remaining_expected_home_goals"],
                            model["remaining_expected_away_goals"],
                            *model["current_score"])
    probabilities = one_x_two(grid)
    if any(not math.isclose(probability, model["fulltime_probabilities"][outcome],
                            rel_tol=0, abs_tol=1e-12)
           for outcome, probability in probabilities.items()):
        raise ReplayDistributionError("MATRIX_MISMATCH")

    distributions = [market_distribution(grid, **request) for request in markets]
    if any(not math.isclose(math.fsum(distribution["outcome_probabilities"].values()),
                            1.0, rel_tol=0, abs_tol=1e-9)
           for distribution in distributions):
        raise ReplayDistributionError("MASS_MISMATCH")
    return {"probabilities_1x2": probabilities, "diagnostic_distributions": distributions}


def replay(envelope, digest, now):
    try:
        model = audit_bound_predict(envelope, digest, now)
        if model.get("status") != "RESEARCH_ONLY":
            return hold(model.get("reason", "MODEL_HELD"))
        distributions = replay_distributions(model, (
            {"market": "totals", "side": "UNDER", "line": 2.25},
            {"market": "asian_handicap", "side": "HOME", "line": 1.25},
        ))
        return {**hold("UNAUTHENTICATED_RESEARCH_REPLAY"), "replay_status":"RESEARCH_ONLY",
                "fixture_id":model["fixture_id"], **distributions, "model_edge":None,
                "actual_xg":None, "actual_quote_verified":False}
    except ReplayDistributionError as error:
        return hold(str(error))
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError, RecursionError):
        return hold("INVALID_REPLAY")
