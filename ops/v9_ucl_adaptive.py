"""V9 integrated research: fixed causal adaptive UCL weighting, no promotion."""
import argparse,json,math
from collections import defaultdict,deque
from pathlib import Path
from datetime import date
from ops import v8_ucl_strength as u,v8_ucl_gap_fill as g,v8_ucl_opponent as o,v8_ucl_calibration as c
from ops import v5_ensemble_competition as e
from ops.v6_forward_bundle import decode
WINDOW=192
MIN_HISTORY=96
SCALE=.08
def weight(history):
    if len(history)<MIN_HISTORY:return .5
    advantage=sum(b-a for a,b in history)/len(history)
    # Positive advantage means attack/defence model had lower loss.
    return .2+.6/(1+math.exp(-max(-20.,min(20.,advantage/SCALE))))
def adaptive(rows):
    days=defaultdict(list);seen=set()
    for r in rows:
        date.fromisoformat(r["date"])
        k=(r["date"],r["home"],r["away"])
        if k in seen or type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("INVALID_CASE")
        seen.add(k);days[r["date"]].append(r)
    hist=deque(maxlen=WINDOW);out=[]
    for day in sorted(days):
        w=weight(hist)
        group=sorted(days[day],key=lambda r:(r["home"],r["away"]))
        for r in group:
            p,q=e.vec(r["baseline"]),e.vec(r["elo"])
            out.append({**r,"fixed":e.vec(r["hybrid"]),"adaptive":e.vec([w*a+(1-w)*b for a,b in zip(p,q)]),"attack_weight":w,"prior_n":len(hist)})
        for r in group:hist.append((e.loss(e.vec(r["baseline"]),r["y"]),e.loss(e.vec(r["elo"]),r["y"])))
    return out
def evaluate(rows):
    rows=adaptive(rows)
    dev=[r for r in rows if r["season"] in c.DEV]
    test=[r for r in rows if r["season"]==c.TEST]
    if len(dev)!=336 or len(test)!=144 or any(r["date"]<"2025-07-01" for r in test):raise ValueError("COHORT")
    fixed_params=c.fit(dev)
    adaptive_params=c.fit([{**r,"hybrid":r["adaptive"]} for r in dev])
    fn={"v8_fixed":lambda r:r["fixed"],"v8_calibrated":lambda r:c.calibrate(r["fixed"],*fixed_params),
        "v9_adaptive":lambda r:r["adaptive"],"v9_adaptive_calibrated":lambda r:c.calibrate(r["adaptive"],*adaptive_params)}
    def scores(rows):return {k:e.metrics(rows,f) for k,f in fn.items()}
    common=[r for r in test if max(r["fixed"])>=.5]
    result=scores(test)
    return {"schema":"v9-ucl-adaptive-research-v1","development_n":len(dev),"assessment_n":len(test),
        "assessment":result,"same_fixed_selected":{"n":len(common),"metrics":scores(common)},
        "individual_threshold_50":{k:{"n":len(a),"coverage":len(a)/len(test),"metrics":e.metrics(a,f)} for k,f in fn.items() for a in [[r for r in test if max(f(r))>=.5]]},
        "adaptive_attack_weight":{"min":min(r["attack_weight"] for r in test),"max":max(r["attack_weight"] for r in test),"mean":sum(r["attack_weight"] for r in test)/len(test)},
        "fixed_params":list(fixed_params),"adaptive_params":list(adaptive_params),
        "window":WINDOW,"weight_bounds":[.2,.8],"assessment_previously_inspected":True,"online_prior_day_results_only":True,
        "proper_score_point_improvement":all(result["v9_adaptive_calibrated"][k]<result["v8_calibrated"][k] for k in ("log_loss","brier")),
        "statistical_promotion_gate":False,"current_fixture_forecasts":0,"verified_forward_sample_credit":0,
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
    cases=o.replay(rows)
    out=evaluate(cases)
    from ops.v9_ucl_goal_strength import evaluate as goal_strength_evaluate
    adaptive_cases=adaptive(cases)
    out["dynamic_goal_strength_challenger"]=goal_strength_evaluate(rows,adaptive_cases)
    from ops.v9_ucl_draw_hurdle import evaluate as hurdle_evaluate
    out["v15_draw_hurdle"]=hurdle_evaluate(rows,adaptive_cases)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
