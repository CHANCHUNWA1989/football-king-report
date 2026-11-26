"""V8.8 UCL probability calibration; exact-label V8.4 comparator, research only."""
import argparse,json,math
from pathlib import Path
from ops import v8_ucl_strength as u,v8_ucl_gap_fill as g,v8_ucl_opponent as o
from ops import v5_ensemble_competition as e
from ops.v6_forward_bundle import decode
from ops.v6_calibration_challenger import reliability

DEV=("2022-23","2023-24","2024-25")
TEST="2025-26"
TEMPS=(.7,.85,1.,1.15,1.3)
SHIFTS=(-.6,-.3,0.,.3,.6)

def calibrate(p,t,h,d):
    if t not in TEMPS or h not in SHIFTS or d not in SHIFTS:raise ValueError("UNKNOWN_PARAMETER")
    z=[math.log(max(v,1e-15))/t+b for v,b in zip(e.vec(p),(h,d,0.))]
    a=[math.exp(v-max(z)) for v in z]
    return e.vec([v/sum(a) for v in a])

def fit(rows):
    if any(r["season"] not in DEV or r["date"]>="2025-07-01" for r in rows):raise ValueError("ASSESSMENT_LEAKAGE")
    if len(rows)<200 or {r["y"] for r in rows}!={0,1,2}:raise ValueError("INSUFFICIENT_DEVELOPMENT")
    candidates=[]
    for t in TEMPS:
        for h in SHIFTS:
            for d in SHIFTS:
                penalty=(t-1)**2+h*h+d*d
                loss=sum(e.loss(calibrate(r["hybrid"],t,h,d),r["y"]) for r in rows)/len(rows)
                candidates.append((loss+.04*penalty,penalty,t,h,d))
    return min(candidates)[2:]

def profile(rows,fn):
    return [{"class":i,"observed":sum(r["y"]==i for r in rows)/len(rows),
        "mean_probability":sum(fn(r)[i] for r in rows)/len(rows),
        "top_prediction_count":sum(max(range(3),key=lambda k:fn(r)[k])==i for r in rows),
        "correct_class_count":sum(r["y"]==i and max(range(3),key=lambda k:fn(r)[k])==i for r in rows)} for i in range(3)]

def evaluate(rows):
    dev=[];test=[];seen=set()
    for r in rows:
        k=(r["date"],r["home"],r["away"])
        if k in seen or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("INVALID_CASE")
        seen.add(k);e.vec(r["hybrid"])
        if r["season"] in DEV:dev.append(r)
        elif r["season"]==TEST:
            if r["date"]<"2025-07-01":raise ValueError("ASSESSMENT_CLOCK")
            test.append(r)
    if len(test)!=144:raise ValueError("ASSESSMENT_COVERAGE")
    par=fit(dev)
    base=lambda r:r["hybrid"]
    cand=lambda r:calibrate(base(r),*par)
    b,c=e.metrics(test,base),e.metrics(test,cand)
    common=[r for r in test if max(base(r))>=.5]
    def selected(fn):
        a=[r for r in test if max(fn(r))>=.5]
        return {"n":len(a),"coverage":len(a)/len(test),"metrics":e.metrics(a,fn)}
    return {"schema":"v8-8-ucl-calibration-research-v1","development_seasons":DEV,"development_n":len(dev),"assessment_season":TEST,"assessment_n":len(test),
        "parameters":{"temperature":par[0],"home_log_shift":par[1],"draw_log_shift":par[2]},
        "baseline":b,"candidate":c,"baseline_class_profile":profile(test,base),"candidate_class_profile":profile(test,cand),
        "baseline_reliability":reliability(test,base),"candidate_reliability":reliability(test,cand),
        "same_baseline_selected":{"n":len(common),"baseline":e.metrics(common,base),"candidate":e.metrics(common,cand)},
        "individual_threshold_50":{"baseline":selected(base),"candidate":selected(cand)},
        "historical_point_scores_improved":c["log_loss"]<b["log_loss"] and c["brier"]<b["brier"],
        "statistical_promotion_gate":False,"assessment_previously_inspected":True,"historical_aliases_used":False,
        "prospective_validation":False,"current_fixture_forecasts":0,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}

def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","old-dir","old-manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args()
    old,_=u.load(a.old_dir,decode(Path(a.old_manifest).read_bytes()))
    new,_=g.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    if sorted(r for r in old if r[-1]=="2024-25")!=sorted(r for r in new if r[-1]=="2024-25"):raise ValueError("OVERLAP_CONFLICT")
    rows=sorted([r for r in old if r[-1]!="2024-25"]+new)
    if len(rows)!=1536:raise ValueError("COHORT_SIZE")
    out=evaluate(o.replay(rows))
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in out.items() if not k.endswith("_reliability")},allow_nan=False))
if __name__=="__main__":main()
