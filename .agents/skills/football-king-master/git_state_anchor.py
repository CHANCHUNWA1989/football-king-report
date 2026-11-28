"""V3.3 isolated Git checkpoint store. External trusted tip required; no deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import continuity as v
import deployment_checkpoint as c
import research_queue as q

REF="refs/heads/research-state"
ZERO="0"*40
MAX_GENERATIONS=64
MAX_BUNDLE=32*1024*1024
FLAGS=dict(**v.FLAGS,permanentHostingVerified=False)
def require(ok,reason):
    if not ok: raise ValueError(reason)
def oid(x):
    require(isinstance(x,str) and re.fullmatch(r"[0-9a-f]{40}",x) and x!=ZERO,"INVALID_GIT_ID")
    return x
def outside(path):
    p=Path(path).absolute()
    require(p==p.resolve() and p!=q.ROOT and q.ROOT not in p.parents,"ISOLATED_PATH_REQUIRED")
    return p
def invoke(args,raw=None):
    env={"PATH":os.defpath+"/usr/local/bin","LANG":"C.UTF-8","GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null","GIT_AUTHOR_NAME":"Football King research fixture","GIT_AUTHOR_EMAIL":"research@example.invalid","GIT_COMMITTER_NAME":"Football King research fixture","GIT_COMMITTER_EMAIL":"research@example.invalid","GIT_TERMINAL_PROMPT":"0"}
    r=subprocess.run(["git","-c","core.hooksPath=/dev/null",*args],input=raw,capture_output=True,timeout=20,env=env)
    if r.returncode: raise RuntimeError("GIT_OPERATION_FAILED")
    require(len(r.stdout)<=MAX_BUNDLE,"GIT_OUTPUT_LIMIT")
    return r.stdout
def git(store,args,raw=None):
    p=outside(store)
    require(p.is_dir() and not p.is_symlink(),"STORE_REQUIRED")
    return invoke(["--git-dir",str(p),*args],raw)
def init(store):
    p=outside(store)
    require(not p.exists(),"STORE_EXISTS")
    p.mkdir(mode=0o700)
    invoke(["init","--bare","--object-format=sha1","--initial-branch=research-state",str(p)])
def tip(store):
    out=git(store,["for-each-ref","--format=%(objectname)",REF]).decode().splitlines()
    require(len(out)<=1,"REF_AMBIGUOUS")
    return oid(out[0]) if out else None
def read_version(store,commit):
    oid(commit)
    entries=git(store,["ls-tree",commit]).decode().splitlines()
    require(len(entries)==2,"TREE_SCHEMA")
    names={}
    for line in entries:
        meta,name=line.split("\t")
        mode,kind,blob=meta.split()
        require(mode=="100644" and kind=="blob" and name in ("checkpoint.json","manifest.json") and name not in names,"TREE_ENTRY")
        names[name]=oid(blob)
    require(len(names)==2,"MISSING_BLOB")
    def blob(name,limit):
        size=int(git(store,["cat-file","-s",names[name]]))
        require(size<=limit,"BLOB_LIMIT")
        return git(store,["cat-file","blob",names[name]])
    raw=blob("checkpoint.json",c.MAX_BYTES)
    data=v.decode(raw)
    mraw=blob("manifest.json",4096);m=json.loads(mraw)
    require(c.canonical(m)==mraw and set(m)=={"schema","generation","parent","checkpointSha256","lastSlot","cycleCount"},"MANIFEST_SCHEMA")
    require(m["schema"]=="fk-git-state-v1" and type(m["generation"]) is int and 1<=m["generation"]<=MAX_GENERATIONS and m["checkpointSha256"]==hashlib.sha256(raw).hexdigest() and bool(data["cycles"]) and m["lastSlot"]==data["cycles"][-1]["slot"] and m["cycleCount"]==len(data["cycles"]),"MANIFEST_BINDING")
    parents=git(store,["rev-list","--parents","-n","1",commit]).decode().split()
    require(parents[0]==commit and len(parents) in (1,2),"PARENT_SCHEMA")
    parent=parents[1] if len(parents)==2 else None
    require(m["parent"]==parent,"PARENT_BINDING")
    return dict(**m,raw=raw,commit=commit)
def latest(store,trusted_tip):
    oid(trusted_tip)
    require(tip(store)==trusted_tip,"TRUSTED_TIP_MISMATCH")
    head=read_version(store,trusted_tip);child=head
    while child["parent"] is not None:
        parent=read_version(store,child["parent"])
        require(parent["generation"]+1==child["generation"],"GENERATION_ROLLBACK")
        v.successor(parent["raw"],child["raw"])
        child=parent
    require(child["generation"]==1,"GENESIS_GENERATION")
    require(tip(store)==trusted_tip,"TIP_CHANGED_DURING_READ")
    return head
def publish(store,raw,expected):
    data=v.decode(raw);require(bool(data["cycles"]),"EMPTY_STATE")
    require(tip(store)==expected,"CAS_STALE")
    generation=1
    if expected is not None:
        old=latest(store,expected)
        v.successor(old["raw"],raw)
        generation=old["generation"]+1
    require(generation<=MAX_GENERATIONS,"GENERATION_LIMIT")
    manifest=dict(schema="fk-git-state-v1",generation=generation,parent=expected,checkpointSha256=hashlib.sha256(raw).hexdigest(),lastSlot=data["cycles"][-1]["slot"],cycleCount=len(data["cycles"]))
    blobs=[oid(git(store,["hash-object","-w","--stdin"],b).decode().strip()) for b in (raw,c.canonical(manifest))]
    tree=oid(git(store,["mktree"],("100644 blob "+blobs[0]+"\tcheckpoint.json\n100644 blob "+blobs[1]+"\tmanifest.json\n").encode()).decode().strip())
    args=["commit-tree",tree]+(["-p",expected] if expected else [])
    commit=oid(git(store,args,b"Research state checkpoint\n").decode().strip())
    # Compare and swap in Git itself. Never force, merge, reset or fall back.
    git(store,["update-ref",REF,commit,expected or ZERO])
    return commit
def backup(store,expected,bundle):
    latest(store,expected)
    p=outside(bundle)
    require(not p.exists(),"BACKUP_EXISTS")
    git(store,["bundle","create",str(p),REF])
    require(p.is_file() and p.stat().st_size<=MAX_BUNDLE,"BUNDLE_LIMIT")
    require(tip(store)==expected,"TIP_CHANGED_DURING_BACKUP")
    refs=invoke(["bundle","list-heads",str(p)]).decode().splitlines()
    require(refs==[expected+" "+REF],"BUNDLE_TIP_MISMATCH")
def recover(bundle,dest,expected):
    oid(expected)
    p=outside(bundle);out=outside(dest)
    require(p.is_file() and p.stat().st_size<=MAX_BUNDLE and not out.exists(),"RECOVERY_PATH")
    refs=invoke(["bundle","list-heads",str(p)]).decode().splitlines()
    require(refs==[expected+" "+REF],"BUNDLE_TIP_MISMATCH")
    invoke(["clone","--bare","--no-local",str(p),str(out)])
    latest(out,expected)
    return dict(**FLAGS,restored=True,tip=expected,anchorAuthenticated=False)
def review_gate(head,author,reviews):
    oid(head);require(isinstance(author,str) and author.strip() and isinstance(reviews,list),"REVIEW_INPUT")
    significant={};ids=set()
    for r in sorted(reviews,key=lambda r:r["id"]):
        require(type(r["id"]) is int and r["id"]>0 and r["id"] not in ids,"REVIEW_ID")
        ids.add(r["id"])
        login=r["user"]["login"];state=r["state"]
        require(isinstance(login,str) and login.strip() and state in ("APPROVED","CHANGES_REQUESTED","DISMISSED","COMMENTED","PENDING"),"REVIEW_SCHEMA")
        if login.lower()==author.lower() or state in ("COMMENTED","PENDING"): continue
        significant[login.lower()]=r
    approvals=sum(r["state"]=="APPROVED" and r["commit_id"]==head and r["author_association"] in ("OWNER","MEMBER","COLLABORATOR") for r in significant.values())
    blockers=sum(r["state"]=="CHANGES_REQUESTED" for r in significant.values())
    return dict(**FLAGS,candidateApprovals=approvals,blockingReviews=blockers,reviewCount=len(reviews),reviewStatus="BLOCKED_INDEPENDENT_REVIEW_REQUIRED")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["review","drill"])
    p.add_argument("paths",type=Path,nargs="+")
    a=p.parse_args()
    try:
        if a.command=="review" and len(a.paths)==2:
            pr=json.loads(v.read(a.paths[0]));reviews=json.loads(v.read(a.paths[1]))
            require(pr["head"]["repo"]["full_name"]==v.REPO and pr["base"]["repo"]["full_name"]==v.REPO and pr["number"]==788,"PR_IDENTITY")
            out=review_gate(pr["head"]["sha"],pr["user"]["login"],reviews)
        elif a.command=="drill" and len(a.paths)==2:
            raw=v.read(a.paths[0]);base=outside(a.paths[1]);base.mkdir(mode=0o700)
            store=base/"state.git";init(store);commit=publish(store,raw,None)
            bundle=base/"state.bundle";backup(store,commit,bundle)
            restored=base/"recovered.git";recover(bundle,restored,commit)
            state=latest(restored,commit)
            require(state["raw"]==raw,"ROUNDTRIP")
            c.restore(base/"sqlite",state["raw"],state["checkpointSha256"])
            out=dict(**FLAGS,status="GIT_STATE_DRILL_OK",tip=commit,generation=state["generation"],checkpointSha256=state["checkpointSha256"],bundleBytes=bundle.stat().st_size,restored=True,anchorAuthenticated=False)
        else: raise ValueError("ARGS")
        print(json.dumps(out,sort_keys=True));return 0
    except Exception as e:
        print(json.dumps(dict(**FLAGS,status="BLOCKED",reason=str(e) if isinstance(e,ValueError) else type(e).__name__)))
        return 1
if __name__=="__main__": raise SystemExit(main())
