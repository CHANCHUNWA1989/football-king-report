"""Bounded conversion from finite score grids into v2 archive cells.

The discarded mass is measured from the supplied grid, not a bound on the
unseen mass of the underlying model. No independent model-tail attestation.
"""
from collections.abc import Mapping
from math import fsum,isfinite
from ops.prospective_score_archive_v2_20261127 import grid_from_cells

MAX_SCORE=30
MAX_DISCARDED=1e-10
MASS_TOL=1e-10

def export_cells(grid):
    if not isinstance(grid,Mapping) or not grid:
        raise ValueError("nonempty score grid required")
    retained=[];discarded=[]
    for score,p in grid.items():
        if not isinstance(score,tuple) or len(score)!=2 or any(type(v) is not int or v<0 for v in score):
            raise ValueError("invalid score")
        if type(p) not in (int,float) or not isfinite(p) or not 0<=p<=1:
            raise ValueError("invalid probability")
        if max(score)>MAX_SCORE: discarded.append(p)
        else: retained.append((*score,p))
    mass=fsum(grid.values());lost=fsum(discarded)
    if abs(mass-1)>MASS_TOL or not retained:
        raise ValueError("source mass invalid")
    kept=fsum(p for _,_,p in retained)
    fraction=lost/mass
    if fraction>MAX_DISCARDED or kept<=0:
        raise ValueError("score support truncation exceeds budget")
    cells=[[h,a,p/kept] for h,a,p in sorted(retained) if p>0]
    grid_from_cells(cells)
    return {"score_cells":cells,"input_mass":mass,"discarded_mass":lost,
            "discarded_fraction":fraction,"conditional_event_error_bound":fraction,
            "underlying_model_tail_verified":False,"deployment":"HOLD",
            "recommendations":"DISABLED"}

def score_delta_bound(discarded_fraction):
    if type(discarded_fraction) not in (int,float) or not isfinite(discarded_fraction) or not 0<=discarded_fraction<=MAX_DISCARDED:
        raise ValueError("invalid discarded fraction")
    # For any event indicator, conditioning on retained support changes
    # its probability by at most the discarded fraction. This does not
    # bound log loss for arbitrarily rare exact scores.
    return {"event_probability_bound":discarded_fraction,
            "exact_score_log_loss_bound":None,"model_tail_verified":False}
