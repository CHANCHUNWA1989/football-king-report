"""Single-source research pricing from one validated score distribution.

This is a research bridge, NOT production integration. No odds-feed verification.
"""
from __future__ import annotations
import math
from typing import Sequence
from ops.research_multimodel_v1 import score_matrix, dixon_coles, probabilities
from ops.research_asian_settlement_v1 import asian_ev

def unified_research_pricing(home_xg: float, away_xg: float, *,
                             handicap_line: float, totals_line: float,
                             handicap_home_odds: float, handicap_away_odds: float,
                             over_odds: float, under_odds: float,
                             dc_rho: float | None=None) -> dict:
    """Every market shares the exact same normalized score matrix.

    All handicap lines are expressed from home team's perspective.
    Explicit decimal odds are hypothetical until independently verified.
    """
    matrix=(score_matrix(home_xg,away_xg) if dc_rho is None else
            dixon_coles(home_xg,away_xg,dc_rho))
    one_x_two=probabilities(matrix)
    markets={
        "handicap_home":asian_ev(matrix,market="handicap",selection="home",
                                  line=handicap_line,decimal_odds=handicap_home_odds),
        "handicap_away":asian_ev(matrix,market="handicap",selection="away",
                                  line=handicap_line,decimal_odds=handicap_away_odds),
        "totals_over":asian_ev(matrix,market="totals",selection="over",
                                line=totals_line,decimal_odds=over_odds),
        "totals_under":asian_ev(matrix,market="totals",selection="under",
                                 line=totals_line,decimal_odds=under_odds)}
    mass=sum(map(sum,matrix))
    if abs(mass-1)>1e-8 or abs(sum(one_x_two.values())-1)>1e-8:
        raise ValueError("inconsistent unified distribution")
    return {"schema":"football-king-unified-research-pricing-v1",
            "status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
            "score_matrix_size":len(matrix),"score_mass":mass,
            "one_x_two":one_x_two,"markets":markets,
            "odds_verified":False,"positive_ev_verified":False,
            "qualified_for_production":False}
