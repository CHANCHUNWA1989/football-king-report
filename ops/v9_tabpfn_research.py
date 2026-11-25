"""V12 optional local TabPFN benchmark. No auto-download or production use.
Use a separately licensed, locally provisioned checkpoint in an isolated
network-disabled environment. Historical comparison, not prospective evidence.
"""
import argparse
import hashlib
import hmac
import json
import math
import os
from datetime import date
from importlib.metadata import version
from pathlib import Path
from ops import v8_multiseason as v,v8_same_fixture as s
from ops import v5_ml_benchmark as ml,v5_ensemble_competition as e
from ops.v6_forward_bundle import decode

VERSION="10.2.0"
FILENAMES=("tabpfn-v3.5-20260909.safetensors","tabpfn-v3.5-fast-20260909.safetensors",
           "tabpfn-v3.5-20260909_multiclass.safetensors")
TRAIN=("2022-23","2023-24")
CAL="2024-25"
TEST="2025-26"
MIN=200
MAX=5000
GRID=(0.,.25,.5,.75,1.)
TEMPERATURES=(.8,1.,1.2,1.5)
BATCH=64

def checkpoint(path,digest,reviewed):
    p=Path(path)
    if reviewed is not True:raise ValueError("LICENSE_REVIEW_REQUIRED")
    if p.name not in FILENAMES or p.is_symlink() or not p.is_file():
        raise ValueError("LOCAL_CHECKPOINT_REQUIRED")
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("CHECKPOINT_DIGEST")
    if not 0<p.stat().st_size<=3_000_000_000:raise ValueError("CHECKPOINT_SIZE")
    with p.open("rb") as f:actual=hashlib.file_digest(f,"sha256").hexdigest()
    if not hmac.compare_digest(actual,digest):raise ValueError("CHECKPOINT_HASH_MISMATCH")
    return p.resolve()

def partition(data):
    out={"train":[],"cal":[],"test":[]};seen=set();totals={}
    for league in v.LEAGUES:
        for season in (*TRAIN,CAL,TEST):
            raw=data[season,league]
            if season==TEST:totals[league]=len(raw)
            for r in ml.features(s.document(raw)):
                d=date.fromisoformat(r["date"]);year=int(season[:4])
                key=(league,*e.key(r))
                if not date(year,7,1)<=d<date(year+1,7,1) or key in seen:
                    raise ValueError("FOUNDATION_FIXTURE_CLOCK")
                seen.add(key)
                x=[float(a) for a in r["x"]]+[float(league==k) for k in v.LEAGUES]
                if len(x)!=19 or not all(math.isfinite(a) for a in x):raise ValueError("FOUNDATION_FEATURES")
                part="train" if season in TRAIN else "cal" if season==CAL else "test"
                out[part].append({**r,"x":x,"league":league,"season":season})
    for part in out.values():
        part.sort(key=lambda r:(r["date"],r["league"],r["home"],r["away"]))
        if not MIN<=len(part)<=MAX or {r["y"] for r in part}!={0,1,2}:raise ValueError("FOUNDATION_COVERAGE")
    return out,totals

def predict(model,rows):
    if list(model.classes_)!=[0,1,2]:raise ValueError("FOUNDATION_CLASS_ORDER")
    result=[]
    for i in range(0,len(rows),BATCH):
        x=[r["x"] for r in rows[i:i+BATCH]]
        p=model.predict_proba(x)
        if len(p)!=len(x):raise ValueError("FOUNDATION_PREDICTION_COUNT")
        result.extend(e.vec([float(a) for a in q]) for q in p)
    return result

def temper(p,t):
    if t not in TEMPERATURES:raise ValueError("FOUNDATION_TEMPERATURE")
    z=[max(x,1e-15)**(1/t) for x in e.vec(p)]
    return e.vec([x/sum(z) for x in z])

def blend(p,q,t,w):
    if w not in GRID:raise ValueError("FOUNDATION_WEIGHT")
    return e.vec([(1-w)*a+w*b for a,b in zip(e.vec(p),temper(q,t))])

def calibrate(rows,reference,foundation):
    if len(rows)<MIN or len(rows)!=len(reference) or len(rows)!=len(foundation) or any(r["season"]!=CAL for r in rows):
        raise ValueError("FOUNDATION_CAL_SCOPE")
    def objective(pair):
        t,w=pair
        loss=math.fsum(e.loss(blend(p,q,t,w),r["y"]) for r,p,q in zip(rows,reference,foundation))/len(rows)
        return loss+.005*w*w+.001*(t-1)**2,w,abs(t-1),t
    return min(((t,w) for t in TEMPERATURES for w in GRID),key=objective)

def run(data,*,checkpoint_path,sha256,license_reviewed,device="cpu"):
    p=checkpoint(checkpoint_path,sha256,license_reviewed)
    if device not in ("cpu","cuda"):raise ValueError("FOUNDATION_DEVICE")
    if version("tabpfn")!=VERSION:raise ValueError("FOUNDATION_PACKAGE_VERSION")
    # These flags supplement, not replace, OS-level network isolation.
    os.environ["HF_HUB_OFFLINE"]="1"
    os.environ["TRANSFORMERS_OFFLINE"]="1"
    from tabpfn import TabPFNClassifier
    from ops.v9_league_weights import ci
    parts,totals=partition(data)
    tr,cal,test=(parts[k] for k in ("train","cal","test"))
    models={k:ml.classifier(k) for k in ml.BACKENDS}
    models["tabpfn"]=TabPFNClassifier(model_path=p,device=device,n_estimators=4,
        random_state=42,ignore_pretraining_limits=False)
    predictions={}
    for name,model in models.items():
        model.fit([r["x"] for r in tr],[r["y"] for r in tr])
        predictions[name]={"cal":predict(model,cal),"test":predict(model,test)}
    # Choose reference only on calibration season, not assessment.
    ref=min(ml.BACKENDS,key=lambda k:(sum(e.loss(p,r["y"]) for p,r in zip(predictions[k]["cal"],cal))/len(cal),k))
    t,w=calibrate(cal,predictions[ref]["cal"],predictions["tabpfn"]["cal"])
    rows=[]
    for i,r in enumerate(test):
        q={k:p["test"][i] for k,p in predictions.items()}
        rows.append({**r,**q,"reference":q[ref],"candidate":blend(q[ref],q["tabpfn"],t,w)})
    def metrics(a,total):
        if not a or len(a)>total:raise ValueError("FOUNDATION_SCOPE")
        m={k:e.metrics(a,lambda r:r[k]) for k in (*models,"reference","candidate")}
        interval=ci([{**r,"hybrid":r["reference"]} for r in a])
        return {"n":len(a),"all_finished":total,"coverage":len(a)/total,"metrics":m,
                "paired_week_ci_reference_minus_candidate":interval,
                "historical_proper_score_gate":bool(interval and interval[0]>0 and all(m["candidate"][k]<m["reference"][k] for k in ("log_loss","brier")))}
    return {"schema":"v12-tabpfn-local-foundation-research-v1","package_version":VERSION,
        "checkpoint_filename":p.name,"checkpoint_sha256":sha256,"device":device,"estimators":4,
        "features":list(ml.FEATURE_NAMES)+list(v.LEAGUES),"training_n":len(tr),
        "calibration_n":len(cal),"assessment_n":len(test),"reference_model":ref,
        "selected_temperature":t,"selected_foundation_weight":w,
        "pooled":metrics(rows,sum(totals.values())),
        "per_league":{k:metrics([r for r in rows if r["league"]==k],totals[k]) for k in v.LEAGUES},
        "assessment_previously_inspected":True,"pretraining_overlap_unknown":True,
        "direct_v11_3_comparison":False,"actual_xg_used":False,"prospective_validation":False,
        "verified_forward_sample_credit":0,"automatic_promotion":False,
        "production_recommendations":"DISABLED","status":"HOLD"}

def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","checkpoint","sha256","output"):p.add_argument("--"+k,required=True)
    p.add_argument("--license-reviewed",action="store_true");p.add_argument("--device",choices=("cpu","cuda"),default="cpu")
    a=p.parse_args()
    checkpoint(a.checkpoint,a.sha256,a.license_reviewed)
    data,_=v.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    out=run(data,checkpoint_path=a.checkpoint,sha256=a.sha256,license_reviewed=a.license_reviewed,device=a.device)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
