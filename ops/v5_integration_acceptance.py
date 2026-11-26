"""V5 phase 8: score-distribution settlement integration, research only.
No odds/EV, production deployment, or synthetic evidence admission.
"""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import importlib.util
import json
import math
from pathlib import Path

from ops.asian_handicap_research import grade as legacy_handicap_grade
from ops.live_market_research import payout as legacy_payout

GRADES=("FULL_WIN","HALF_WIN","PUSH","HALF_LOSS","FULL_LOSS")
GRADE={2:GRADES[0],1:GRADES[1],0:GRADES[2],-1:GRADES[3],-2:GRADES[4]}

def units(line,kind):
    if isinstance(line,bool) or not isinstance(line,(int,float,str,Decimal)):
        raise ValueError("INVALID_LINE")
    try:d=Decimal(str(line))
    except InvalidOperation as e:raise ValueError("INVALID_LINE") from e
    if not d.is_finite() or d*4!=(d*4).to_integral_value():
        raise ValueError("INVALID_QUARTER_LINE")
    if kind=="handicap" and -5<=d<=5 or kind=="totals" and 0<=d<=12:
        return int(d*4)
    raise ValueError("OUT_OF_RANGE")

def settlement(h,a,kind,side,line):
    if any(type(v) is not int or not 0<=v<=65 for v in (h,a)):
        raise ValueError("INVALID_GRID_SCORE")
    q=units(line,kind)
    legs=(q-1,q+1) if q%2 else (q,q)
    if kind=="handicap" and side in ("home","away"):
        value=4*(h-a if side=="home" else a-h)
        signed=[value+l for l in legs]
    elif kind=="totals" and side in ("over","under"):
        signed=[(4*(h+a)-l)*(1 if side=="over" else -1) for l in legs]
    else:raise ValueError("BAD_MARKET_SIDE")
    return GRADE[sum((v>0)-(v<0) for v in signed)]

def grid(h,a,rh,ra):
    if any(type(v) is not int or not 0<=v<=25 for v in (h,a)):
        raise ValueError("BAD_CURRENT_SCORE")
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=8 for v in (rh,ra)):
        raise ValueError("BAD_REMAINING_RATE")
    def weights(r):
        p=[math.exp(-r)]
        for i in range(1,41):p.append(p[-1]*r/i)
        return p
    values={(h+i,a+j):p*q for i,p in enumerate(weights(rh)) for j,q in enumerate(weights(ra))}
    mass=math.fsum(values.values())
    if not 1-1e-12<=mass<=1+1e-12:raise ValueError("TRUNCATION_MASS")
    return {k:v/mass for k,v in values.items()}

def project(g,kind,side,line):
    out=dict.fromkeys(GRADES,0.)
    for (h,a),v in g.items():out[settlement(h,a,kind,side,line)]+=v
    if abs(sum(out.values())-1)>1e-10:raise ValueError("INVALID_GRADE_MASS")
    return out

def summary(g):
    p=[0.,0.,0.];totals=Counter();margins=Counter()
    for (h,a),v in g.items():
        p[0 if h>a else 1 if h==a else 2]+=v
        totals[str(h+a)]+=v;margins[str(h-a)]+=v
    return {"1x2":p,"final_total_p":dict(totals),"final_margin_p":dict(margins)}

def cross_engine():
    n=0
    for h in range(7):
        for a in range(7):
            for kind,sides,lines in (("handicap",("home","away"),range(-20,21)),
                                     ("totals",("over","under"),range(0,49))):
                for side in sides:
                    for q in lines:
                        line=q/4;g=settlement(h,a,kind,side,line)
                        if kind=="handicap" and g!=legacy_handicap_grade(h,a,side.upper(),line):
                            raise ValueError("LEGACY_GRADE_MISMATCH")
                        # Decimal 2 is a fixed synthetic unit-payout test, NOT a quote.
                        v=legacy_payout({"kind":kind,"side":side,"line":line,"odds":2.},h,a)
                        if v!={"FULL_WIN":1.,"HALF_WIN":.5,"PUSH":0.,"HALF_LOSS":-.5,"FULL_LOSS":-1.}[g]:
                            raise ValueError("LEGACY_PAYOUT_MISMATCH")
                        n+=1
    return n

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def historical(train,test,joint):
    tr,te=joint.parse(train),joint.parse(test)
    if not tr or not te or max(r[0] for r in tr)>=min(r[0] for r in te):
        raise ValueError("OVERLAPPING_SEASONS")
    m=joint.fit(tr,min(r[0] for r in te))
    markets=(("handicap","home",-.25),("handicap","away",.25),
             ("totals","over",2.25),("totals","under",2.25))
    sums={str(k):{"observed":Counter(),"predicted":Counter(),"brier_sum":0.} for k in markets}
    n=0;excluded=0
    for _,h,a,x,y in te:
        r=joint.rates(m,h,a)
        if r is None or not all(.05<=v<=8 for v in r):
            excluded+=1;continue
        g=grid(0,0,*r)
        for k in markets:
            p=project(g,*k);actual=settlement(x,y,*k);s=sums[str(k)]
            s["observed"][actual]+=1;s["predicted"].update(p)
            s["brier_sum"]+=sum((p[v]-(v==actual))**2 for v in GRADES)
        n+=1
    if not n:raise ValueError("EMPTY_COHORT")
    return {"n":n,"excluded":excluded,"markets":{k:{"observed":dict(s["observed"]),
        "mean_grade_probabilities":{v:s["predicted"][v]/n for v in GRADES},
        "five_grade_brier":s["brier_sum"]/n} for k,s in sums.items()},
        "hypothetical_lines_only":True,"actual_market_quotes":False,"independent_results":False}

def readiness(evidence,quality,market):
    if any(not isinstance(v,dict) or v.get("production_recommendations")!="DISABLED" for v in (evidence,quality,market)):
        raise ValueError("UNSAFE_SOURCE")
    rows=evidence.get("samples")
    if not isinstance(rows,list) or type(evidence.get("n")) is not int or evidence["n"]!=len(rows):
        raise ValueError("INVALID_EVIDENCE")
    return {"recorded_research_samples":len(rows),"independently_authenticated_forward_samples":0,
            "quality_gates_reported_passed":quality.get("passed"),"quality_gates_total":quality.get("total"),
            "market_collection_status":market.get("collection_status"),
            "market_collection_reason":market.get("collection_reason"),
            "market_snapshot_utc":market.get("as_of_utc"),
            "release_status":"HOLD","production_recommendations":"DISABLED",
            "production_deployed":False,"model_promoted":False,
            "blockers":["INDEPENDENT_FORWARD_EVIDENCE_NOT_CONNECTED","LIVE_TWO_SOURCE_AND_XG_UNQUALIFIED",
                        "EXECUTABLE_MARKET_PRICE_NOT_VERIFIED","INDEPENDENT_REVIEW_PENDING"]}

def main():
    p=argparse.ArgumentParser();p.add_argument("--train",required=True);p.add_argument("--assessment",required=True)
    p.add_argument("--joint",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    def read(path):
        f=Path(path)
        if f.stat().st_size>2_000_000:raise ValueError("INPUT_LIMIT")
        return json.loads(f.read_text())
    result={"schema":"v5-integration-acceptance-v1","synthetic_cross_engine_checks":cross_engine(),
            "historical":historical(read(a.train),read(a.assessment),load(a.joint,"joint")),
            "readiness":readiness(read("evidence/settled.json"),read("sources/seven_quality_gates_latest.json"),read("market/collection_status.json")),
            "assessment_previously_inspected":True,"prospective_validation":False,
            "ensemble_1x2_not_converted_to_goal_rates":True,"production_recommendations":"DISABLED"}
    Path(a.output).write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,allow_nan=False))
if __name__=="__main__":main()
