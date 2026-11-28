"""V3.8 synthetic-only multi-file Git migration. No production or provider access."""
import hashlib
import json
import sys
import tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
import git_state_anchor as g
import asia_migration as a

STREAMS=("market-consensus","market-status","secondary-sources","six-league-coverage","quality-gates","fixture-overlap")
LIMIT=16
EPOCH=datetime(2026,1,1,tzinfo=timezone.utc)
FLAGS=dict(release="HOLD",production_recommendations="DISABLED",classification="SYNTHETIC_ONLY",providerCalls=0,deploymentAuthorized=False,githubProtectionVerified=False)
def require(ok,reason):
    if not ok: raise ValueError(reason)
def canonical(obj): return (json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def fixture(batch,offset):
    require(type(batch) is int and 1<=batch<=9999 and type(offset) is int and 0<=offset<=100000,"FIXTURE_RANGE")
    return {k:canonical(dict(schema="fk-migration-fixture-v1",stream=k,batch=batch,captured_utc=(EPOCH+timedelta(seconds=offset+i)).isoformat(),classification="SYNTHETIC_ONLY",release="HOLD",production_recommendations="DISABLED",observations=[])) for i,k in enumerate(STREAMS)}
def decode(raw):
    require(isinstance(raw,bytes) and len(raw)<=16384,"SIZE")
    return json.loads(raw,object_pairs_hook=a.unique)
def validate(docs):
    require(isinstance(docs,dict) and set(docs)==set(STREAMS),"COMPLETE_BATCH_REQUIRED")
    parsed={}
    for i,k in enumerate(STREAMS):
        d=decode(docs[k]);require(isinstance(d,dict),"OBJECT_REQUIRED")
        n=d.get("batch");require(type(n) is int and 1<=n<=9999,"BATCH_ID")
        stamp=d.get("captured_utc");require(isinstance(stamp,str),"TIME")
        dt=datetime.fromisoformat(stamp)
        require(dt.tzinfo is not None and dt.utcoffset()==timedelta(0),"UTC_REQUIRED")
        offset=(dt-EPOCH).total_seconds()-i
        require(offset.is_integer() and 0<=offset<=100000,"TIME_RANGE")
        require(d==json.loads(fixture(n,int(offset))[k]),"SYNTHETIC_SHAPE")
        parsed[k]=d
    ids={d["batch"] for d in parsed.values()}
    require(len(ids)==1,"MIXED_BATCH")
    return ids.pop(),{k:parsed[k]["captured_utc"] for k in STREAMS}
def tip(store): return g.tip(store)
def hist(n,k): return f"history-{n:04d}-{k}.json"
def latest_name(k): return "latest-"+k+".json"
def blob(store,raw): return g.oid(g.git(store,["hash-object","-w","--stdin"],raw).decode().strip())
def read_blob(store,oid):
    require(int(g.git(store,["cat-file","-s",g.oid(oid)]))<=16384,"BLOB_LIMIT")
    return g.git(store,["cat-file","blob",oid])
def read_tree(store,commit):
    tree={}
    for line in g.git(store,["ls-tree","-r",g.oid(commit)]).decode().splitlines():
        meta,name=line.split("\t");mode,kind,oid=meta.split()
        require(mode=="100644" and kind=="blob" and name not in tree and "/" not in name,"TREE_ENTRY")
        tree[name]=g.oid(oid)
    require(len(tree)<=1+6*(LIMIT+1),"TREE_LIMIT")
    return tree
def commit_tree(store,parent,tree):
    data="".join("100644 blob "+g.oid(tree[k])+"\t"+k+"\n" for k in sorted(tree)).encode()
    t=g.oid(g.git(store,["mktree"],data).decode().strip())
    return g.oid(g.git(store,["commit-tree",t]+(["-p",g.oid(parent)] if parent else []),b"Synthetic atomic migration batch\n").decode().strip())
def manifest(n,times,docs,parent,gen):
    return dict(schema="fk-batch-migration-v1",classification="SYNTHETIC_ONLY",release="HOLD",production_recommendations="DISABLED",batch=n,generation=gen,parent=parent,streams={k:dict(captured_utc=times[k],sha256=sha(docs[k])) for k in STREAMS})
def read_version(store,commit):
    tree=read_tree(store,commit)
    require("manifest.json" in tree and all(latest_name(k) in tree for k in STREAMS),"MISSING_FILE")
    docs={k:read_blob(store,tree[latest_name(k)]) for k in STREAMS};n,times=validate(docs)
    m=decode(read_blob(store,tree["manifest.json"]))
    require(isinstance(m,dict) and type(m.get("generation")) is int and 1<=m["generation"]<=LIMIT,"MANIFEST_GEN")
    p=g.git(store,["rev-list","--parents","-n","1",commit]).decode().split()
    require(p[0]==commit and len(p) in (1,2),"PARENT")
    parent=p[1] if len(p)==2 else None
    require(m==manifest(n,times,docs,parent,m["generation"]) and type(m["batch"]) is int,"MANIFEST")
    require(all(tree.get(hist(n,k))==tree[latest_name(k)] for k in STREAMS),"HISTORY_LATEST_MISMATCH")
    return dict(tree=tree,docs=docs,batch=n,times=times,parent=parent,generation=m["generation"])
def chain(store,commit):
    head=read_version(store,commit);cur=head
    for _ in range(LIMIT):
        current_paths={hist(cur["batch"],k) for k in STREAMS}
        expected={"manifest.json"}|{latest_name(k) for k in STREAMS}|current_paths
        if cur["parent"] is None:
            require(cur["generation"]==1 and set(cur["tree"])==expected,"GENESIS")
            return head
        prev=read_version(store,cur["parent"])
        old_history={k:v for k,v in prev["tree"].items() if k.startswith("history-")}
        require(cur["generation"]==prev["generation"]+1 and cur["batch"]>prev["batch"],"VERSION_ROLLBACK")
        require(all(datetime.fromisoformat(cur["times"][k])>datetime.fromisoformat(prev["times"][k]) for k in STREAMS),"TIME_ROLLBACK")
        require(not current_paths.intersection(old_history) and set(cur["tree"])==expected|set(old_history),"HISTORY_LAYOUT")
        require(all(cur["tree"][k]==v for k,v in old_history.items()),"HISTORY_REWRITE")
        cur=prev
    raise ValueError("CHAIN_LIMIT")
def latest(store,expected,require_tip=True):
    g.oid(expected)
    if require_tip: require(tip(store)==expected,"TRUSTED_TIP")
    out=chain(store,expected)
    if require_tip: require(tip(store)==expected,"TIP_CHANGED")
    return out
def build(store,docs,parent,old,fail=False):
    n,times=validate(docs);gen=1 if old is None else old["generation"]+1
    require(gen<=LIMIT,"GENERATION_LIMIT")
    tree={} if old is None else {k:v for k,v in old["tree"].items() if k.startswith("history-")}
    for k in STREAMS:
        p=hist(n,k);require(p not in tree,"IMMUTABLE_COLLISION")
        tree[p]=tree[latest_name(k)]=blob(store,docs[k])
    tree["manifest.json"]=blob(store,canonical(manifest(n,times,docs,parent,gen)))
    if fail: raise RuntimeError("INJECTED_BEFORE_COMMIT")
    result=commit_tree(store,parent,tree);chain(store,result);return result
def init(remote,docs):
    g.init(remote);g.git(remote,["config","receive.denyNonFastForwards","true"]);g.git(remote,["config","receive.denyDeletes","true"])
    x=build(remote,docs,None,None);g.git(remote,["update-ref",g.REF,x,g.ZERO]);return x
def clone(remote,dest): return a.clone(remote,dest)
def prepare(writer,expected,docs,fail_before_commit=False):
    old=latest(writer,expected);n,times=validate(docs)
    if old["docs"]==docs:return expected
    require(n>old["batch"],"BATCH_COLLISION_OR_REPLAY")
    require(all(datetime.fromisoformat(times[k])>datetime.fromisoformat(old["times"][k]) for k in STREAMS),"STALE_STREAM")
    return build(writer,docs,expected,old,fail_before_commit)
def push(writer,remote,commit):
    info=chain(writer,commit)
    require(info["parent"]==tip(writer) or commit==tip(writer),"WRITER_PARENT")
    return a.push(writer,remote,commit)
def delete_drill(writer,remote): return a.delete_drill(writer,remote)
def backup(store,expected,bundle):
    latest(store,expected);p=g.outside(bundle);require(not p.exists(),"BACKUP_EXISTS")
    g.git(store,["bundle","create",str(p),g.REF])
    require(p.stat().st_size<=g.MAX_BUNDLE and g.invoke(["bundle","list-heads",str(p)]).decode().splitlines()==[expected+" "+g.REF],"BUNDLE_TIP")
    latest(store,expected)
def recover(bundle,dest,expected):
    g.oid(expected);p=g.outside(bundle);out=g.outside(dest)
    require(p.is_file() and p.stat().st_size<=g.MAX_BUNDLE and not out.exists(),"RECOVERY_PATH")
    require(g.invoke(["bundle","list-heads",str(p)]).decode().splitlines()==[expected+" "+g.REF],"BUNDLE_TIP")
    g.invoke(["-c","protocol.file.allow=always","clone","--bare","--no-local",str(p),str(out)])
    latest(out,expected);return out
def drill():
    with tempfile.TemporaryDirectory() as t:
        p=Path(t);remote=p/"remote.git";first=init(remote,fixture(1,0))
        w=clone(remote,p/"writer")
        try: prepare(w,first,fixture(2,20),fail_before_commit=True)
        except RuntimeError: pass
        else: raise ValueError("FAULT_NOT_INJECTED")
        require(tip(remote)==first and len(latest(remote,first)["tree"])==13,"PARTIAL_PUBLISH")
        second=prepare(w,first,fixture(2,20));require(tip(remote)==first and push(w,remote,second),"PUBLISH")
        w2=clone(remote,p/"writer2");third=prepare(w2,second,fixture(3,40));require(push(w2,remote,third),"PUBLISH")
        require(not delete_drill(w2,remote),"DELETE")
        bundle=p/"copy.bundle";backup(remote,third,bundle);out=latest(recover(bundle,p/"recovered.git",third),third)
        require(out["docs"]==fixture(3,40) and len(out["tree"])==25,"RESTORE")
        return dict(**FLAGS,status="BATCH_MIGRATION_DRILL_OK",generation=3,streams=6,immutableHistoryFiles=18,latestFiles=6,treeFiles=25,failedPreparationLeftRefUnchanged=True,restored=True,bundleBytes=bundle.stat().st_size,rawSha256={k:sha(v) for k,v in out["docs"].items()})
if __name__=="__main__":
    if sys.argv[1:]!=["--drill"]:raise SystemExit(2)
    print(json.dumps(drill(),sort_keys=True))
