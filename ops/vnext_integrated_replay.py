"""Offline VNext research replay. No authenticated data, EV or release."""
import math
from live_snapshot_commitment import audit_bound_predict
from live_snapshot_adapter import hold
from inplay_state_challenger_vnext import remaining_matrix
from score_distribution_vnext import one_x_two, market_distribution

def replay(envelope, digest, now):
    try:
        model = audit_bound_predict(envelope, digest, now)
        if model.get("status") != "RESEARCH_ONLY":
            return hold(model.get("reason", "MODEL_HELD"))
        grid = remaining_matrix(model["remaining_expected_home_goals"],
                                model["remaining_expected_away_goals"],
                                *model["current_score"])
        probs = one_x_two(grid)
        if any(not math.isclose(p, model["fulltime_probabilities"][k],
                                rel_tol=0, abs_tol=1e-12) for k,p in probs.items()):
            return hold("MATRIX_MISMATCH")
        markets = [market_distribution(grid, market="totals", side="UNDER", line=2.25),
                   market_distribution(grid, market="asian_handicap", side="HOME", line=1.25)]
        if any(not math.isclose(math.fsum(m["outcome_probabilities"].values()),
                                1., rel_tol=0, abs_tol=1e-9) for m in markets):
            return hold("MASS_MISMATCH")
        return {**hold("UNAUTHENTICATED_RESEARCH_REPLAY"), "replay_status":"RESEARCH_ONLY",
                "fixture_id":model["fixture_id"], "probabilities_1x2":probs,
                "diagnostic_distributions":markets, "model_edge":None,
                "actual_xg":None, "actual_quote_verified":False}
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError, RecursionError):
        return hold("INVALID_REPLAY")
