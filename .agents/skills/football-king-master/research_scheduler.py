"""V3.0 bounded scheduled research cycles; explicit execution, no live data calls."""
import argparse
import json
import secrets
import time
from pathlib import Path
import sys
import research_queue as q
import cross_review as review

PERIOD=21600
FLAGS=dict(**q.FLAGS,continuousOperationVerified=False,independentAgentReviews=0)
def slot(now):
    if type(now) is not int or now<0:
        raise ValueError("CLOCK_INVALID")
    return now-now%PERIOD
def init(directory):
    q.init(directory)
    with q._tx(directory) as db:
        db.execute("""CREATE TABLE cycles(slot INTEGER PRIMARY KEY,status TEXT NOT NULL
            CHECK(status IN('RUNNING','SUCCEEDED','BLOCKED','RETRY_WAIT')),
            token TEXT,summary TEXT NOT NULL)""")
def claim(directory, when):
    if slot(when)!=when:
        raise ValueError("SLOT_INVALID")
    with q._tx(directory) as db:
        if q._stopped(db) or db.execute("SELECT 1 FROM cycles WHERE status IN('RUNNING','BLOCKED') OR slot>=?",(when,)).fetchone():
            return None
        token=secrets.token_hex(16)
        db.execute("INSERT INTO cycles VALUES(?, 'RUNNING',?, '{}')",(when,token))
        return token
def finish(directory, when, token, outcome, summary):
    if outcome not in ("SUCCEEDED","BLOCKED","RETRY_WAIT") or not token:
        raise ValueError("INVALID_OUTCOME")
    with q._tx(directory) as db:
        if q._stopped(db):
            outcome="BLOCKED"
        result=db.execute("UPDATE cycles SET status=?,token=NULL,summary=? WHERE slot=? AND status='RUNNING' AND token=?",
            (outcome,json.dumps(summary,sort_keys=True),when,token))
        if result.rowcount!=1:
            raise ValueError("CYCLE_TOKEN_MISMATCH")
    return outcome
def status(directory):
    with q._tx(directory) as db:
        return dict(**FLAGS,stopped=q._stopped(db),periodSeconds=PERIOD,
            cycles=[dict(slot=r["slot"],status=r["status"],summary=json.loads(r["summary"])) for r in db.execute("SELECT slot,status,summary FROM cycles ORDER BY slot")])
def require(ok, reason):
    if not ok: raise ValueError(reason)
def check_result(stage, result, binding):
    require(isinstance(result,dict) and result.get("release")=="HOLD" and result.get("production_recommendations")=="DISABLED","SAFETY_FLAGS")
    files=binding.get("files",{})
    ledger=files.get("evidence/settled.json")
    if stage=="diagnose":
        expected={k:files[k] for k in ("evidence/settled.json","market/latest.json","sources/seven_quality_gates_latest.json")}
        require(result.get("sourceHashes")==expected and result.get("automaticProductionRepair") is False and isinstance(result.get("issues"),list),"DIAGNOSIS_BINDING")
        require(all(isinstance(x,dict) and x.get("action") in ("EXTERNAL_EVIDENCE_REQUIRED","REFRESH_VIA_APPROVED_COLLECTOR_ONLY","NO_VENDOR_CALL","NO_EXTRA_VENDOR_CALL") for x in result["issues"]),"UNSAFE_DIAGNOSIS")
        return {"issues":result["issues"]}
    if stage=="evidence":
        require(result.get("ledgerSha256")==ledger and result.get("certifiedN")==0 and result.get("certified") is False and result.get("classification")=="HISTORICAL_UNAUTHENTICATED_ONLY","EVIDENCE_CONTRACT")
        return {"historicalN":result["historicalN"],"certifiedN":0,"newForwardRecords":0}
    if stage=="model":
        require(result.get("ledgerSha256")==ledger and result.get("valid") is True and result.get("certifiedN")==0 and result.get("canPromote") is False and result.get("canChangeWeights") is False and result.get("classification")=="RETROSPECTIVE_PROXY_ONLY","MODEL_CONTRACT")
        return {"evaluatedN":result["evaluatedN"],"certifiedN":0,"drift":result["drift"]["status"]}
    if stage=="review":
        require(result.get("binding")==binding and result.get("status")=="AUTOMATED_CHECKS_COMPLETE" and result.get("checkedRoles")==4 and type(result.get("independentAgentReviews")) is int and result["independentAgentReviews"]==0 and result.get("mergeAuthorized") is False and result.get("canPromote") is False and result.get("reviewStatus")=="BLOCKED_INDEPENDENT_REVIEW_REQUIRED","REVIEW_CONTRACT")
        return {"checkedRoles":4,"independentAgentReviews":0}
    raise ValueError("UNKNOWN_STAGE")
def run(directory):
    when=slot(int(time.time()))
    token=claim(directory,when)
    if token is None:
        current=status(directory)
        blocked=current["stopped"] or any(r["status"] in ("RUNNING","BLOCKED") for r in current["cycles"])
        return "BLOCKED" if blocked else "NO_CLAIM"
    summary={"stages":{},"vendorCalls":0,"newForwardRecords":0}
    outcome="BLOCKED"
    try:
        before=review.binding()
        summary["binding"]=before
        def guard():
            require(not q.snapshot(directory)["stopped"],"STOPPED")
            require(review.binding()==before,"INPUT_CHANGED")
        def stage(name,args):
            guard()
            result=json.loads(review.command(args,timeout=90))
            summary["stages"][name]=check_result(name,result,before)
        stage("diagnose",["node",str(q.SKILL/"recovery.mjs"),"--diagnose"])
        guard()
        key=q.fingerprint()
        q.enqueue(directory,key,now=int(time.time()))
        job=next(r for r in q.snapshot(directory)["jobs"] if r["id"]==key)
        if job["status"]=="SUCCEEDED":
            summary["stages"]["hub"]={"status":"REUSED_IDENTICAL_CONTENT","attempts":job["attempts"]}
        else:
            result=q.run_once(directory)
            job=next(r for r in q.snapshot(directory)["jobs"] if r["id"]==key)
            if job["status"]=="RETRY_WAIT" and result in ("TRANSIENT","NO_CLAIM"):
                outcome="RETRY_WAIT"
                summary["stages"]["hub"]={"status":"RETRY_WAIT","attempts":job["attempts"]}
                return finish(directory,when,token,outcome,summary)
            require(result=="SUCCESS" and job["status"]=="SUCCEEDED","HUB_BLOCKED")
            summary["stages"]["hub"]={"status":"EXECUTED","attempts":job["attempts"]}
        stage("evidence",["node",str(q.SKILL/"evidence-chain.mjs"),"--audit"])
        stage("model",["node",str(q.SKILL/"calibration.mjs"),"--ledger","evidence/settled.json"])
        stage("review",[sys.executable,str(q.SKILL/"cross_review.py"),"--run"])
        guard()
        summary["inputsUnchanged"]=True
        outcome="SUCCEEDED"
    except Exception as exc:
        summary["reason"]=type(exc).__name__
    return finish(directory,when,token,outcome,summary)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["init","run","status","stop"])
    p.add_argument("directory",type=Path)
    a=p.parse_args()
    try:
        result={}
        if a.command=="init": init(a.directory)
        elif a.command=="stop": q.stop(a.directory)
        elif a.command=="run": result["cycleOutcome"]=run(a.directory)
        print(json.dumps(dict(**status(a.directory),**result),sort_keys=True))
        return 1 if result.get("cycleOutcome") in ("BLOCKED","RETRY_WAIT") else 0
    except Exception as exc:
        print(json.dumps(dict(**FLAGS,status="BLOCKED",reason=type(exc).__name__)))
        return 1
if __name__=="__main__": raise SystemExit(main())
