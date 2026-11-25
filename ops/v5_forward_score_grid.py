"""Operational shadow projection on existing V4.1 rates, not V5 ensemble.
New completion timestamp, strict upstream candidate gates, no production release.
"""
import argparse
import gzip
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
import sys

from ops.v5_integration_acceptance import grid,project,summary
sys.path.insert(0,str(Path(__file__).resolve().parent))
from model_dixon_coles_forward import build as upstream_build, _utc, _unique_object, _nonfinite

MODEL="v5-score-grid-v41-rate-forward-shadow-v1"
LIMIT=8_000_000
LINES=(("handicap","home",-.25),("handicap","away",.25),
       ("totals","over",2.25),("totals","under",2.25))

def forward(shadow,source_sha,*,clock=None,upstream=None):
    clock=clock or (lambda:datetime.now(timezone.utc))
    upstream=upstream or upstream_build
    start=clock()
    if not isinstance(start,datetime) or start.utcoffset() is None:
        raise ValueError("INVALID_RUNTIME_CLOCK")
    result=upstream(shadow)
    candidates=[]
    exclusions={}
    for row in result.get("predictions",[]):
        try:
            g=grid(0,0,row["expected_home_goals"],row["expected_away_goals"])
            s=summary(g)
            if max(abs(x-y) for x,y in zip(s["1x2"],row["derived_rho0"]))>1.1e-5:
                raise ValueError("RATE_COHERENCE")
            candidates.append({"event_id":row["event_id"],"league":row["league"],
                "home":row["home"],"away":row["away"],"recorded_kickoff_utc":row["kickoff_utc_recorded"],
                "source_prediction_utc":row["source_prediction_utc"],
                "source_projection_sha256":row["source_projection_sha256"],
                "model_id":MODEL,"source_model":row["source_model"],
                "expected_goals":[row["expected_home_goals"],row["expected_away_goals"]],
                "distribution":s,"fixed_line_grade_probabilities":[{"kind":k,"side":side,"line":line,
                    "grade_probabilities":project(g,k,side,line)} for k,side,line in LINES],
                "production_recommendations":"DISABLED"})
        except (ValueError,KeyError,TypeError,OverflowError):
            exclusions["INVALID_PROJECTION"]=exclusions.get("INVALID_PROJECTION",0)+1
    end=clock()
    if not isinstance(end,datetime) or end.utcoffset() is None:raise ValueError("INVALID_RUNTIME_CLOCK")
    source_at=result.get("source_as_of_utc")
    if end<start or not source_at or not 0<=(end-_utc(source_at)).total_seconds()<=36000:
        candidates=[]
        exclusions["SOURCE_OR_RUNTIME_CLOCK_INVALID"]=1
    rows=[]
    for row in candidates:
        if (_utc(row["recorded_kickoff_utc"])-end).total_seconds()<=600:
            exclusions["INSUFFICIENT_KICKOFF_LEAD"]=exclusions.get("INSUFFICIENT_KICKOFF_LEAD",0)+1
            continue
        row["prediction_utc"]=end.isoformat();rows.append(row)
    return {"schema":"v5-forward-score-grid-research-v1","model_id":MODEL,
        "status":"SHADOW_ONLY" if rows else "HOLD","generated_utc":end.isoformat(),
        "source_archive_sha256":source_sha,"source_as_of_utc":source_at,
        "source_problem":result.get("source_problem"),"upstream_exclusions":result.get("exclusions",{}),
        "projection_exclusions":exclusions,"predictions_count":len(rows),"predictions":rows,
        "source_rates_are_v41":True,"v5_ensemble_live_integration":False,
        "independent_source_authentication":False,"external_capture_witness_verified":False,
        "verified_forward_sample_credit":0,"actual_market_lines":False,"ev_verified":False,
        "production_recommendations":"DISABLED","model_promoted":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--input",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    f=Path(a.input)
    if f.stat().st_size>LIMIT:raise ValueError("COMPRESSED_LIMIT")
    raw=f.read_bytes()
    with gzip.open(f,"rb") as stream:decoded=stream.read(LIMIT+1)
    if len(decoded)>LIMIT:raise ValueError("DECOMPRESSED_LIMIT")
    shadow=json.loads(decoded,object_pairs_hook=_unique_object,parse_constant=_nonfinite)
    report=forward(shadow,hashlib.sha256(raw).hexdigest())
    with Path(a.output).open("x",encoding="utf-8") as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in report.items() if k!="predictions"},allow_nan=False))
if __name__=="__main__":main()
