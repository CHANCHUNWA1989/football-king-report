"""V25 portable V10.1 shadow model and native eight-expert parity bridge.
No automatic promotion. Historical dates vs HK native date convention and
availability of intervening fixtures are not independently attested.
"""
import math
from collections import defaultdict
from datetime import date, timedelta,datetime,timezone
from ops import v9_stacking_research as s,v9_league_weights as w
from ops import v5_ensemble_competition as e,v5_joint_poisson as joint,v5_dynamic_elo as elo,v5_ml_benchmark as ml
from ops import v8_multiseason as v,v8_same_fixture as same,v5_native_bundesliga_forward as native
from ops.v6_forward_bundle import WEIGHTS,utc,decode
from ops.v20_signed_receipts import bounded,sha
from ops.v21_raw_results import capture
from ops.v23_forward_cycle import validate_capture

def weights(history):
    prior=history[-w.WINDOW:]
    if len(prior)<w.MIN_HISTORY:return dict(w.ANCHOR)
    loss={k:math.fsum(e.loss(r["experts"][k],r["y"]) for r in prior)/len(prior) for k in s.EXPERTS}
    minimum=min(loss.values())
    raw={k:w.ANCHOR[k]*math.exp(-w.TEMPERATURE*(loss[k]-minimum)) for k in s.EXPERTS}
    total=math.fsum(raw.values())
    return {k:(1-w.SHRINK)*w.ANCHOR[k]+w.SHRINK*raw[k]/total for k in s.EXPERTS}

def reference(experts,history):
    q=weights(history)
    return e.vec([math.fsum(q[k]*experts[k][i] for k in s.EXPERTS) for i in range(3)])

def portable(model,row):
    if model.get("schema")!="v25-portable-stack-v1" or model.get("experts")!=list(s.EXPERTS) or model.get("classes")!=[0,1,2]:
        raise ValueError("STACK_MODEL_CONTRACT")
    x=s.features(row);coef=model["coef"];bias=model["intercept"]
    if len(coef)!=3 or len(bias)!=3 or any(len(a)!=len(x) for a in coef) or any(type(z) not in (float,int) or not math.isfinite(z) or abs(z)>100 for z in [*bias,*[z for a in coef for z in a]]):
        raise ValueError("STACK_COEFFICIENT")
    z=[b+math.fsum(a*t for a,t in zip(c,x)) for c,b in zip(coef,bias)]
    q=[math.exp(a-max(z)) for a in z]
    return e.vec([a/math.fsum(q) for a in q])

def state(train,current):
    if not current or max(r[0] for r in train)>=min(r[0] for r in current):raise ValueError("STACK_NATIVE_ORDER")
    model=joint.fit(train,min(r[0] for r in current))
    cases=ml.features(same.document(train))
    if len(cases)<100 or {r["y"] for r in cases}!={0,1,2}:raise ValueError("STACK_NATIVE_TRAIN")
    models={}
    for k in ml.BACKENDS:
        m=ml.classifier(k);m.fit([r["x"] for r in cases],[r["y"] for r in cases])
        if list(m.classes_)!=[0,1,2]:raise ValueError("STACK_NATIVE_CLASS")
        models[k]=m
    return model,models

def experts_for(train,history,day,h,a,fitted):
    if any(r[0]>=day for r in history):raise ValueError("STACK_NONPRIOR_HISTORY")
    jm,models=fitted;rate=joint.rates(jm,h,a)
    if rate is None or any(not .05<=z<=8 for z in rate):return None
    ratings,teams,prior=native.state(sorted(history),elo)
    er=elo.rates(history,day,h,a,ratings,True)
    f=native.feature(teams,prior,h,a,ml)
    if er is None or f is None:return None
    form={k:[(x,y) for x,y,_ in a] for k,a in teams.items()}
    lh=max(.05,sum(r[3] for r in train)/len(train));la=max(.05,sum(r[4] for r in train)/len(train))
    return {"joint_poisson":e.vec(joint.probability(rate)),"dixon_coles":e.dc(*rate),
        "dynamic_elo":e.vec(elo.probabilities(*er)),
        **{k:e.vec([float(x) for x in m.predict_proba([f])[0]]) for k,m in models.items()},
        "v8":e.dc(*v.rolling_rates(rate,form,h,a,lh,la))}

def paired_rows(train,current,season,*,fitted=None):
    """Native prefix replay, no minimum retrospective assessment sample gate.
    All expert training and per-fixture eligibility requirements stay unchanged.
    """
    fitted=state(train,current) if fitted is None else fitted
    groups=defaultdict(list);seen=set()
    for r in sorted(current):
        day,h,a,x,y=r
        if (day,h,a) in seen:raise ValueError("STACK_NATIVE_DUPLICATE")
        seen.add((day,h,a));groups[day].append(r)
    earlier=[];out=[]
    for day,batch in sorted(groups.items()):
        for _,h,a,x,y in batch:
            q=experts_for(train,earlier,day,h,a,fitted)
            if q is None:continue
            out.append({"league":"de.1","season":season,"date":day.isoformat(),"home":h,"away":a,
                "y":0 if x>y else 1 if x==y else 2,"experts":q})
        earlier.extend(batch)
    return out

def export(rows,data):
    parts=s.partition(rows);m=s.fit_stack(parts["train"])
    def probs(a):return [e.vec([float(x) for x in p]) for p in m.predict_proba([s.features(r) for r in a])]
    t,mix=s.select_calibration(parts["cal"],probs(parts["cal"]))
    model={"schema":"v25-portable-stack-v1","experts":list(s.EXPERTS),"classes":[0,1,2],
        "coef":m.coef_.tolist(),"intercept":m.intercept_.tolist(),"temperature":t,"stack_weight":mix,
        "training_seasons":list(s.TRAIN),"calibration_season":s.CAL,"historical_source_commit":v.PIN,
        "status":"HOLD","production_recommendations":"DISABLED","verified_forward_sample_credit":0}
    test=parts["test"];err=max(abs(x-y) for r,p in zip(test,probs(test)) for x,y in zip(portable(model,r),p))
    if err>1e-10:raise ValueError("STACK_PORTABLE_PARITY")
    german=sorted([r for r in rows if r["league"]=="de.1"],key=e.key)
    maxerr=0.;train=data["2024-25","de.1"];current=data["2025-26","de.1"]
    fitted=state(train,current)
    subset=[r for r in german if r["season"]==s.TEST][-20:]
    if len(subset)!=20:raise ValueError("STACK_PARITY_COHORT")
    for r in subset:
        day=date.fromisoformat(r["date"]);history=[z for z in current if z[0]<day]
        q=experts_for(train,history,day,r["home"],r["away"],fitted)
        if q is None:raise ValueError("STACK_PARITY_MISSING_EXPERT")
        prior=[z for z in german if z["date"]<r["date"]]
        ref=reference(q,prior)
        maxerr=max(maxerr,max(abs(x-y) for k in s.EXPERTS for x,y in zip(q[k],r["experts"][k])),
                   max(abs(x-y) for x,y in zip(ref,r["candidate"])))
    replayed=paired_rows(train,current,s.TEST,fitted=fitted)
    original={e.key(r):r for r in german if r["season"]==s.TEST}
    if {e.key(r) for r in replayed}!=set(original):raise ValueError("STACK_PREFIX_COVERAGE_PARITY")
    prefix_error=max(abs(x-y) for r in replayed for k in s.EXPERTS for x,y in zip(r["experts"][k],original[e.key(r)]["experts"][k]))
    if maxerr>1e-7 or prefix_error>1e-7:raise ValueError("STACK_NATIVE_PARITY")
    tail=[{"date":r["date"],"experts":r["experts"],"y":r["y"]} for r in german[-w.WINDOW:]]
    if len(tail)!=w.WINDOW:raise ValueError("STACK_TAIL")
    return {"schema":"v25-portable-stack-export-v1","model":model,"de1_prior_tail":tail,
        "portable_parity_n":len(test),"portable_max_abs_error":err,"native_feature_parity_n":len(subset),
        "native_feature_max_abs_error":maxerr,"prefix_parity_n":len(replayed),"prefix_max_abs_error":prefix_error,"status":"HOLD","production_recommendations":"DISABLED",
        "verified_forward_sample_credit":0,"automatic_promotion":False}

def infer(bundle,old,new,now):
    if bundle.get("schema")!="v25-portable-stack-export-v1" or bundle.get("status")!="HOLD" or bundle.get("production_recommendations")!="DISABLED" or bundle.get("verified_forward_sample_credit")!=0:
        raise ValueError("STACK_EXPORT_CONTRACT")
    model=bundle["model"]
    year=now.astimezone(native.BERLIN).year-int(now.astimezone(native.BERLIN).month<7)
    if year!=2026:raise ValueError("STACK_EXPORT_SEASON_EXPIRED")
    prior=native.normalize(old,year-1,now,previous=True,shortcut="bl1")
    current=native.normalize(new,year,now,shortcut="bl1")
    tr=joint.parse(prior["history"]);te=joint.parse(current["history"])
    if prior["ids"]&current["ids"]:raise ValueError("STACK_NATIVE_ID_COLLISION")
    season="2026-27";fitted=state(tr,te)
    history=paired_rows(tr,te,season,fitted=fitted)
    tail=bundle["de1_prior_tail"]
    if len(tail)!=w.WINDOW or any(date.fromisoformat(r["date"])>=date(2026,7,1) or type(r["y"]) is not int or r["y"] not in (0,1,2) or set(r["experts"])!=set(s.EXPERTS) for r in tail):
        raise ValueError("STACK_PRIOR_TAIL")
    for r in tail:
        for p in r["experts"].values():e.vec(p)
    if [r["date"] for r in tail]!=sorted(r["date"] for r in tail):raise ValueError("STACK_TAIL_ORDER")
    past=tail+sorted(history,key=e.key);out=[]
    for f in current["fixtures"]:
        ko=utc(f["kickoff_utc"]);day=ko.astimezone(native.HK).date()
        # All known results are from previous HK days, even for future kickoff.
        q=experts_for(tr,[r for r in te if r[0]<day],day,f["h"],f["a"],fitted)
        if q is None:continue
        ref=reference(q,[r for r in past if r["date"]<day.isoformat()])
        p=s.combine(portable(model,{"experts":q}),ref,model["temperature"],model["stack_weight"])
        out.append({**f,"home":current["names"][f["h"]],"away":current["names"][f["a"]],
            "experts":q,"v10_reference":ref,"v10_1_stack":p,"prediction_utc":now.isoformat()})
    return {"schema":"v25-native-stack-shadow-v1","predictions":out,"predictions_count":len(out),
        "eligible_current_history_n":len(history),"scheduled_in_window":len(current["fixtures"]),
        "date_convention":"Asia/Hong_Kong","future_intervening_results_unknown":True,
        "native_historical_identity_crosswalk_verified":False,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}

def live(bundle,*,capture_fn=capture,clock=lambda:datetime.now(timezone.utc)):
    now=clock();year=now.astimezone(native.BERLIN).year-int(now.astimezone(native.BERLIN).month<7)
    if year!=2026:raise ValueError("STACK_EXPORT_SEASON_EXPIRED")
    old,om=capture_fn("openligadb",year-1);new,nm=capture_fn("openligadb",year)
    end=clock();validate_capture(old,om,year-1,end);validate_capture(new,nm,year,end)
    out=infer(bundle,decode(old),decode(new),end);finished=clock()
    if not end<=finished<=end+timedelta(minutes=10) or end.astimezone(native.HK).date()!=finished.astimezone(native.HK).date():raise ValueError("STACK_COMPLETION_CLOCK")
    out["predictions"]=[r for r in out["predictions"] if utc(r["kickoff_utc"])>finished+timedelta(minutes=10)]
    for r in out["predictions"]:r["prediction_utc"]=finished.isoformat()
    out["predictions_count"]=len(out["predictions"]);out["source_receipts"]=[om,nm]
    return out
