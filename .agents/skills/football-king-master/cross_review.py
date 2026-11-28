"""V2.4 deterministic cross-check workers; not independent AI reviewers."""
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SKILL = Path(__file__).resolve().parent
LEDGER = ROOT / "evidence/settled.json"
GATES = ROOT / "sources/seven_quality_gates_latest.json"
MARKET = ROOT / "market/latest.json"
WORKFLOW = ROOT / ".github/workflows/football-king-master-skill.yml"
ROLES = ("code", "data", "model", "risk")
FLAGS = dict(release="HOLD", production_recommendations="DISABLED",
             mergeAuthorized=False, canPromote=False, independentAgentReviews=0)
ENV = {"LANG": "C.UTF-8", "PATH": os.defpath + ":/usr/local/bin:" + str(Path(sys.executable).parent)}
def require(ok, reason):
    if not ok:
        raise ValueError(reason)
def command(args, timeout=30):
    r = subprocess.run(args, cwd=ROOT, env=ENV, capture_output=True, timeout=timeout, check=True)
    require(len(r.stdout) <= 4_000_000, "OUTPUT_LIMIT")
    return r.stdout
def load(p):
    return json.loads(p.read_bytes())
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def binding():
    paths=sorted([p for p in SKILL.iterdir() if p.is_file() and p.suffix in (".mjs",".py",".json",".md")]+[LEDGER,GATES,MARKET,WORKFLOW])
    head=command(["git","rev-parse","HEAD"]).decode().strip()
    require(re.fullmatch(r"[0-9a-f]{40}",head), "HEAD_INVALID")
    hashes={}
    for p in paths:
        relative=str(p.relative_to(ROOT))
        raw=p.read_bytes()
        require(command(["git","show",head+":"+relative])==raw, "CHECKOUT_CONTENT_MISMATCH")
        hashes[relative]=hashlib.sha256(raw).hexdigest()
    return {"checkoutSha":head,"files":hashes}
def utc(s):
    d=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    require(d.tzinfo is not None,"TIMESTAMP_ZONE")
    return d.astimezone(dt.timezone.utc)
def probs(p):
    return isinstance(p,list) and len(p)==3 and all(type(x) in (int,float) and math.isfinite(x) and 0<=x<=1 for x in p) and abs(sum(p)-1)<=1e-6
def rows(doc):
    require(doc["schema"]=="football-king-forward-research-1" and doc["production_recommendations"]=="DISABLED" and type(doc["n"]) is int and doc["n"]==len(doc["samples"]),"LEDGER_SCHEMA")
    counts=collections.Counter(r.get("key") for r in doc["samples"] if isinstance(r,dict))
    result=[]
    for r in doc["samples"]:
        require(isinstance(r,dict) and isinstance(r.get("key"),str),"ROW_SCHEMA")
        if counts[r["key"]]!=1:
            continue
        key=json.loads(r["key"])
        k,f,m=map(utc,(r["kickoff_utc"],r["forecast_utc"],r["market_utc"]))
        require(isinstance(key,list) and len(key)==4 and key[0]==r["league"] and all(isinstance(x,str) and x.strip() for x in key[:3]) and key[1]!=key[2] and utc(key[3])==k,"FIXTURE_KEY")
        require(m<=f<k<utc(doc["checked_utc"]) and type(r["y"]) is int and 0<=r["y"]<=2 and r["production_recommendations"]=="DISABLED" and probs(r["p"]) and probs(r["m"]),"ROW_INVALID")
        result.append((k,f,r))
    return result
def code_check():
    js=sorted(SKILL.glob("*.mjs")); py=sorted(SKILL.glob("*.py"))
    for p in js: command(["node","--check",str(p)])
    for p in py: compile(p.read_text(),str(p),"exec")
    return dict(jsSyntax=len(js),pythonSyntax=len(py),scope="SYNTAX_ONLY_NOT_FULL_CODE_REVIEW")
def data_check():
    doc=load(LEDGER); valid=rows(doc)
    return dict(archiveN=doc["n"],structurallyValidN=len(valid),duplicateExcludedN=doc["n"]-len(valid),
                claimedIndependentN=sum(r.get("fixture_result_source_independently_verified") is True for _,_,r in valid),
                certifiedN=0,sourceAuthentication="NOT_PERFORMED")
def temperature(p,t):
    q=[max(x,1e-15)**(1/t) for x in p]
    return [x/sum(q) for x in q]
def loss(p,y):
    return -math.log(max(p[y],1e-15))
def brier(p,y):
    return sum((x-int(i==y))**2 for i,x in enumerate(p))
def week(f):
    return (f-dt.timedelta(days=f.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
def recalc(doc):
    rr=rows(doc); days=dt.timedelta
    groups=collections.defaultdict(list)
    for k,f,r in rr: groups[week(f)].append((k,f,r))
    folds=[]; pooled=[]
    for start,ev in sorted(groups.items()):
        train=[r for k,f,r in rr if start-days(days=28)<=k+days(days=3)<start and f<start]
        if len(train)<20:
            folds.append((start,len(ev),len(train),None));continue
        grid=(.5,.75,1,1.25,1.5,2)
        t=min(grid,key=lambda t:(sum(loss(temperature(r["p"],t),r["y"]) for r in train)/len(train),abs(t-1),t))
        folds.append((start,len(ev),len(train),t))
        for _,_,r in ev: pooled.append((r["y"],r["p"],temperature(r["p"],t),r["m"]))
    metrics={}
    if pooled:
        for i,name in enumerate(("original","calibrated","market"),1):
            metrics[name]=dict(logLoss=sum(loss(r[i],r[0]) for r in pooled)/len(pooled),brier=sum(brier(r[i],r[0]) for r in pooled)/len(pooled))
    return folds,pooled,metrics
def model_check():
    doc=load(LEDGER);folds,pooled,metrics=recalc(doc)
    j=json.loads(command(["node",str(SKILL/"calibration.mjs"),"--ledger",str(LEDGER)]))
    require(j["ledgerSha256"]==sha(LEDGER) and j["evaluatedN"]==len(pooled) and j["certifiedN"]==0 and j["certifiedMetrics"] is None and j["canChangeWeights"] is False and j["canPromote"] is False and j["classification"]=="RETROSPECTIVE_PROXY_ONLY","MODEL_BOUNDARY")
    require(len(j["folds"])==len(folds),"FOLD_COUNT")
    for (start,n,train,t),f in zip(folds,j["folds"]):
        require(utc(f["start"])==start and f["n"]==n and f["trainN"]==train and f.get("temperature")==t,"FOLD_MISMATCH")
    max_delta=0.
    if not metrics: require(j["metrics"] is None,"EMPTY_METRICS")
    for name,values in metrics.items():
        for key,value in values.items():
            delta=abs(value-j["metrics"][name][key])
            require(math.isfinite(delta) and delta<=1e-10,"CROSS_LANGUAGE_MISMATCH")
            max_delta=max(max_delta,delta)
    return dict(evaluatedN=len(pooled),folds=len(folds),maxAbsoluteMetricDifference=max_delta,metrics=metrics,certifiedN=0,scope="PYTHON_VS_JS_PROXY_ONLY")
def risk_check():
    g=load(GATES); m=load(MARKET); e=load(LEDGER)
    require(g["status"]=="HOLD" and g["can_promote_model"] is False and g["can_recommend_bets"] is False and all(x["production_recommendations"]=="DISABLED" for x in (g,m,e)),"UNSAFE_FLAGS")
    require(g["total"]==7 and len(g["checks"])==7 and len({x["key"] for x in g["checks"]})==7 and all(x["state"] in ("HOLD","PARTIAL","PASS") for x in g["checks"]),"GATE_SCHEMA")
    counts=collections.Counter(x["state"] for x in g["checks"])
    require((counts["PASS"],counts["PARTIAL"],counts["HOLD"])==(g["passed"],g["partial"],g["held"]),"GATE_COUNTS")
    q,p=m["quota"],m["quota_policy"]
    require(all(type(x) is int and x>=0 for x in (q["used"],q["remaining"],p["max_monthly_used"],p["remaining_floor"])),"QUOTA_SCHEMA")
    return dict(gates=dict(counts),quotaHeadroom=min(p["max_monthly_used"]-q["used"],q["remaining"]-p["remaining_floor"]),vendorCalls=0,scope="FLAG_AND_QUOTA_SNAPSHOT_ONLY")
CHECKS=dict(code=code_check,data=data_check,model=model_check,risk=risk_check)
def aggregate(expected, reports):
    require(isinstance(reports,list) and len(reports)==len(ROLES),"MISSING_ROLE")
    seen=set()
    for r in reports:
        require(isinstance(r,dict) and r.get("role") in ROLES and r["role"] not in seen,"DUPLICATE_OR_UNKNOWN_ROLE")
        seen.add(r["role"])
        require(r.get("binding")==expected and r.get("status")=="PASS" and r.get("kind")=="DETERMINISTIC_WORKER" and all(r.get(k)==v and type(r.get(k)) is type(v) for k,v in FLAGS.items()),"WORKER_CONTRACT")
        require(isinstance(r.get("details"),dict),"MISSING_DETAILS")
    return dict(**FLAGS,status="AUTOMATED_CHECKS_COMPLETE",checkedRoles=len(seen),reviewStatus="BLOCKED_INDEPENDENT_REVIEW_REQUIRED",binding=expected,reports=reports)
def worker(role):
    before=binding()
    details=CHECKS[role]()
    require(binding()==before,"INPUT_CHANGED")
    return dict(**FLAGS,role=role,kind="DETERMINISTIC_WORKER",status="PASS",binding=before,details=details)
def main():
    p=argparse.ArgumentParser();p.add_argument("--role",choices=ROLES);p.add_argument("--run",action="store_true");a=p.parse_args()
    try:
        require(bool(a.role)!=a.run,"MODE_REQUIRED")
        if a.role: out=worker(a.role)
        else:
            before=binding()
            reports=[json.loads(command([sys.executable,str(Path(__file__).resolve()),"--role",role],timeout=60)) for role in ROLES]
            require(binding()==before,"INPUT_CHANGED")
            out=aggregate(before,reports)
        print(json.dumps(out,sort_keys=True));return 0
    except Exception as exc:
        print(json.dumps(dict(**FLAGS,status="BLOCKED",reason=type(exc).__name__,reviewStatus="BLOCKED_INDEPENDENT_REVIEW_REQUIRED")))
        return 1
if __name__=="__main__":
    raise SystemExit(main())
