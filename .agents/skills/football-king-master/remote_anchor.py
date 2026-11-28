"""V3.4 read-only qualification of a pinned public synthetic remote anchor."""
import argparse
import hashlib
import json
import pathlib
import sys
import continuity as v
import deployment_checkpoint as c
import git_state_anchor as g

BRANCH="research/master-skill-v34-anchor-drill"
GENESIS="3af8a0491b4dbe2169b8e6ae7241e6cd2ab53cc8"
TIP="5e96e60e64f4ef24f33e1ab12205e50e8597949f"
FLAGS=dict(**g.FLAGS,remoteProductionAnchorVerified=False)
def require(ok,reason):
    if not ok: raise ValueError(reason)
def validate(old,new,manifest,tip,parent):
    require(tip==TIP and parent==GENESIS,"REMOTE_TIP_OR_PARENT")
    require(manifest==dict(schema="fk-v34-remote-drill-v1",generation=2,classification="SYNTHETIC_ONLY",parent=GENESIS,release="HOLD",production_recommendations="DISABLED") and type(manifest["generation"]) is int,"MANIFEST")
    a,b=v.decode(old),v.decode(new)
    require(all(not d["jobs"] and not d["stopped"] and all(r["summary"]=={"synthetic":True} and r["status"]=="SUCCEEDED" for r in d["cycles"]) for d in (a,b)),"SYNTHETIC_ONLY")
    require([r["slot"] for r in a["cycles"]]==[0] and [r["slot"] for r in b["cycles"]]==[0,21600],"FIXTURE_MISMATCH")
    v.successor(old,new)
    return dict(**FLAGS,generation=2,classification="SYNTHETIC_ONLY",checkpointSha256=hashlib.sha256(new).hexdigest(),remoteTip=tip)
def protection(branch,rules):
    p=branch.get("protected") if isinstance(branch,dict) else None
    p=p if type(p) is bool else None
    types=sorted({r["type"] for r in rules if isinstance(r,dict) and isinstance(r.get("type"),str)}) if isinstance(rules,list) else None
    return dict(**FLAGS,protectedReported=p,activeRuleTypes=types,protectionEnforcementVerified=False)
def main():
    p=argparse.ArgumentParser();p.add_argument("store",type=pathlib.Path);p.add_argument("branch_json",type=pathlib.Path);p.add_argument("rules_json",type=pathlib.Path);a=p.parse_args()
    try:
        store=g.outside(a.store)
        ref="refs/heads/"+BRANCH
        tip=g.git(store,["rev-parse",ref]).decode().strip()
        parents=g.git(store,["rev-list","--parents","-n","1",tip]).decode().split()
        require(len(parents)==2 and parents[0]==TIP,"PARENT_COUNT")
        for commit in (TIP,GENESIS):
            require(g.git(store,["ls-tree","--name-only",commit]).decode().splitlines()==["checkpoint.json","manifest.json"],"REMOTE_TREE")
        old=g.git(store,["show",GENESIS+":checkpoint.json"])
        new=g.git(store,["show",TIP+":checkpoint.json"])
        m=json.loads(g.git(store,["show",TIP+":manifest.json"]))
        out=validate(old,new,m,tip,parents[1])
        branch=json.loads(v.read(a.branch_json));rules=json.loads(v.read(a.rules_json))
        require(branch.get("name")==BRANCH and branch.get("commit",{}).get("sha")==TIP,"REMOTE_API_TIP")
        out.update(protection(branch,rules))
        c.restore(store.parent/"restored",new,out["checkpointSha256"])
        require(c.export_bytes(store.parent/"restored")==new,"RESTORE_MISMATCH")
        out.update(status="REMOTE_SYNTHETIC_RESTORE_OK",restored=True)
        print(json.dumps(out,sort_keys=True));return 0
    except Exception as e:
        print(json.dumps(dict(**FLAGS,status="BLOCKED",reason=str(e) if isinstance(e,ValueError) else type(e).__name__)));return 1
if __name__=="__main__": raise SystemExit(main())
