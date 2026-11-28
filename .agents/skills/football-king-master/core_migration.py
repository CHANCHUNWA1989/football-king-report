"""Integrated synthetic core migration qualification; no live signatures or production data."""
import gzip
import hashlib
import json
import sys
import tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
import git_state_anchor as g
import asia_migration as a
import batch_migration as b
sys.path.insert(0,str(g.q.ROOT/"ops"))
import archive_prepare as archive
import archive_forecast_provenance as proof
import evidence_merge as evidence
import model_ab as model_b
import model_market_challenger as model_c

MAX_BATCHES=4
DAY="2026/01/01"
def require(ok,reason):
    if not ok: raise ValueError(reason)
def canonical(x): return b.canonical(x)
def sha(x): return hashlib.sha256(x).hexdigest()
def qualification():
    return dict(release="HOLD",production_recommendations="DISABLED",classification="SYNTHETIC_ONLY",deploymentAuthorized=False,mergeAuthorized=False,signatureAuthenticated=False,independentAgentReviews=0,continuousOperationVerified=False,githubProtectionVerified=False,providerCalls=0)
def fixture(n):
    require(type(n) is int and 1<=n<=9999,"FIXTURE_ID")
    kickoff=datetime(2026,1,1,12,tzinfo=timezone.utc)+timedelta(minutes=n)
    p=[.4,.3,.3];m=[.3,.4,.3]
    s=dict(key=f"synthetic-fixture-{n}",league="synthetic",kickoff_utc=kickoff.isoformat(),forecast_utc=(kickoff-timedelta(hours=1)).isoformat(),market_utc=(kickoff-timedelta(hours=2)).isoformat(),p=p,m=m,ab=model_b.candidate(p),ab_model=model_b.MODEL,c=model_c.candidate(p,m),c_model=model_c.MODEL,fixture_result_source_independently_verified=False,production_recommendations="DISABLED")
    snapshots={k:canonical(dict(classification="SYNTHETIC_ONLY",batch=n,kind=k,prediction=s,production_recommendations="DISABLED")) for k in (*archive.FOLDERS,*archive.OPTIONAL_FOLDERS)}
    proofs={}
    for k in proof.FILES:
        if k.endswith(".log"): raw=b"Synthetic rejection report; NOT verified\n"
        elif k.endswith(".verification.json"): raw=canonical([{"synthetic":True,"signatureAuthenticated":False}])
        elif k=="negative_checks.json": raw=canonical(dict(tampered_subject_rejected=True,wrong_source_digest_rejected=True))
        elif k=="research.sigstore.json": raw=canonical(dict(synthetic=True,signatureAuthenticated=False))
        elif k=="shadow.json": raw=snapshots["shadow"]
        elif k=="paired.json": raw=snapshots["paired"]
        else: raw=snapshots["slate"]
        proofs[k]=raw
    ledger=dict(schema=evidence.SCHEMA,checked_utc=(kickoff+timedelta(hours=3)).isoformat(),samples=[dict(s,y=n%3)],n=1,results_independently_verified=False,profitability_verified=False,production_recommendations="DISABLED")
    return dict(batch=n,snapshots=snapshots,proof=proofs,ledger=ledger)
def validate(f):
    require(isinstance(f,dict) and set(f)=={"batch","snapshots","proof","ledger"},"FIXTURE_FIELDS")
    n=f["batch"]; expected=fixture(n)
    rows=evidence.validate(f["ledger"])
    require(len(rows)==1 and evidence.aware(f["ledger"]["checked_utc"])>evidence.aware(rows[0]["kickoff_utc"]),"SETTLEMENT_TIME")
    require(f==expected,"SYNTHETIC_FIXTURE_OR_SEAL_MISMATCH")
    return n
def payload(f):
    n=validate(f)
    with tempfile.TemporaryDirectory() as t:
        root=Path(t);snap=root/"snap";pr=root/"proof";dst=root/"out"
        for p in (snap,pr,dst): p.mkdir()
        for k,v in f["snapshots"].items(): (snap/(k+".json")).write_bytes(v)
        for k,v in f["proof"].items(): (pr/k).write_bytes(v)
        ap=archive.prepare(snap,dst,n,1,day=DAY)
        pp=proof.prepare(pr,dst,n,1,day=DAY)
        require(len(ap)==5 and len(pp)==10,"ARCHIVE_COUNT")
        require(archive.prepare(snap,dst,n,1,day=DAY)==[] and proof.prepare(pr,dst,n,1,day=DAY)==[],"IDEMPOTENT_ARCHIVE")
        out={}
        for k,folder in {**archive.FOLDERS,**archive.OPTIONAL_FOLDERS}.items():
            path=dst/folder/DAY/(str(n)+"-1.json.gz")
            raw=path.read_bytes();require(gzip.decompress(raw)==f["snapshots"][k],"ARCHIVE_BYTES")
            out[f"batch-{n:04d}-snapshot-{k}.gz"]=raw
        for k in proof.FILES:
            raw=(dst/"forecast_provenance"/DAY/(str(n)+"-1")/(k+".gz")).read_bytes()
            require(gzip.decompress(raw)==f["proof"][k],"PROOF_BYTES")
            out[f"batch-{n:04d}-proof-{k}.gz"]=raw
        return out
def manifest(parent,ids,files):
    return dict(schema="fk-core-migration-v1",parent=parent,batches=ids,hashes={k:sha(v) for k,v in files.items()},**qualification())
def read(store,commit):
    tree=b.read_tree(store,commit);require("manifest.json" in tree and "ledger.json" in tree,"TREE")
    files={k:b.read_blob(store,v) for k,v in tree.items()}
    m=b.decode(files.pop("manifest.json"));ids=m.get("batches")
    require(isinstance(ids,list) and 1<=len(ids)<=MAX_BATCHES and all(type(n) is int and 1<=n<=9999 for n in ids) and ids==sorted(set(ids)),"BATCH_IDS")
    parents=g.git(store,["rev-list","--parents","-n","1",commit]).decode().split()
    require(parents[0]==commit and len(parents) in (1,2),"PARENT")
    parent=parents[1] if len(parents)==2 else None
    require(m==manifest(parent,ids,files),"MANIFEST")
    ledger=b.decode(files["ledger.json"]);evidence.validate(ledger)
    require([s["key"] for s in ledger["samples"]]==[f"synthetic-fixture-{n}" for n in ids],"LEDGER_KEYS")
    expected={}
    for n,sample in zip(ids,ledger["samples"]):
        f=fixture(n);require(sample==f["ledger"]["samples"][0],"HISTORICAL_LEDGER_CHANGED")
        expected.update(payload(f))
    require(set(files)==set(expected)|{"ledger.json"} and all(files[k]==v for k,v in expected.items()),"HISTORY_BYTES")
    require(evidence.aware(ledger["checked_utc"])==max(evidence.aware(fixture(n)["ledger"]["checked_utc"]) for n in ids),"CHECKED_TIME")
    return dict(files={**files,"manifest.json":canonical(m)},ledger=ledger,ids=ids,parent=parent)
def chain(store,commit):
    first=read(store,commit);cur=first
    for _ in range(MAX_BATCHES):
        if cur["parent"] is None:
            require(len(cur["ids"])==1,"GENESIS");return first
        prev=read(store,cur["parent"])
        require(cur["ids"][:-1]==prev["ids"] and all(cur["files"][k]==v for k,v in prev["files"].items() if k.startswith("batch-")),"CHAIN_REWRITE")
        cur=prev
    raise ValueError("CHAIN_LIMIT")
def latest(store,expected):
    require(g.tip(store)==g.oid(expected),"TRUSTED_TIP")
    x=chain(store,expected)
    require(g.tip(store)==expected,"TIP_CHANGED")
    return x
def build(store,parent,old,f,fail=False):
    n=validate(f);ids=[] if old is None else old["ids"]
    require(len(ids)<MAX_BATCHES and (not ids or n>ids[-1]),"BATCH_ORDER")
    files={} if old is None else {k:v for k,v in old["files"].items() if k.startswith("batch-")}
    files.update(payload(f));ledger=evidence.merge(None if old is None else old["ledger"],f["ledger"])
    files["ledger.json"]=canonical(ledger)
    files["manifest.json"]=canonical(manifest(parent,ids+[n],files))
    tree={k:b.blob(store,v) for k,v in files.items()}
    if fail: raise RuntimeError("INJECTED_BEFORE_COMMIT")
    x=b.commit_tree(store,parent,tree);chain(store,x);return x
def init(store):
    g.init(store);g.git(store,["config","receive.denyNonFastForwards","true"]);g.git(store,["config","receive.denyDeletes","true"])
    x=build(store,None,None,fixture(1));g.git(store,["update-ref",g.REF,x,g.ZERO]);return x
def prepare(writer,expected,f,fail=False):
    old=latest(writer,expected);n=validate(f)
    if n in old["ids"]:
        require(n==old["ids"][-1],"STALE_REPLAY")
        return expected
    return build(writer,expected,old,f,fail)
def push(writer,remote,commit):
    x=chain(writer,commit);require(x["parent"]==g.tip(writer) or commit==g.tip(writer),"WRITER_PARENT")
    return a.push(writer,remote,commit)
def backup(store,expected,bundle):
    latest(store,expected);p=g.outside(bundle);require(not p.exists(),"BACKUP_EXISTS")
    g.git(store,["bundle","create",str(p),g.REF])
    require(p.stat().st_size<=g.MAX_BUNDLE and g.invoke(["bundle","list-heads",str(p)]).decode().splitlines()==[expected+" "+g.REF],"BUNDLE_TIP")
    latest(store,expected)
def recover(bundle,dest,expected):
    p=g.outside(bundle);out=g.outside(dest);g.oid(expected)
    require(p.is_file() and p.stat().st_size<=g.MAX_BUNDLE and not out.exists(),"RECOVER_PATH")
    require(g.invoke(["bundle","list-heads",str(p)]).decode().splitlines()==[expected+" "+g.REF],"BUNDLE_TIP")
    g.invoke(["-c","protocol.file.allow=always","clone","--bare","--no-local",str(p),str(out)])
    latest(out,expected);return out
def drill():
    with tempfile.TemporaryDirectory() as t:
        root=Path(t);remote=root/"remote.git";first=init(remote)
        w=a.clone(remote,root/"writer")
        try: prepare(w,first,fixture(2),fail=True)
        except RuntimeError: pass
        else: raise ValueError("FAULT_NOT_INJECTED")
        require(g.tip(remote)==first,"PARTIAL_PUBLICATION")
        one=prepare(w,first,fixture(2));require(push(w,remote,one),"PUBLISH")
        w2=a.clone(remote,root/"writer2");two=prepare(w2,one,fixture(3));require(push(w2,remote,two),"PUBLISH")
        bundle=root/"copy.bundle";backup(remote,two,bundle)
        x=latest(recover(bundle,root/"restored.git",two),two)
        require(x["files"]==latest(remote,two)["files"] and x["ledger"]["n"]==3,"RESTORE")
        return dict(**qualification(),status="CORE_MIGRATION_DRILL_OK",archiveFiles=15,historyFiles=45,ledgerRows=3,treeFiles=len(x["files"]),bundleBytes=bundle.stat().st_size,rawBytesPreserved=True,failedPreparationLeftRefUnchanged=True)
if __name__=="__main__":
    if sys.argv[1:]!=["--drill"]:raise SystemExit(2)
    print(json.dumps(drill(),sort_keys=True))
