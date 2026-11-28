"""V3.7 synthetic-only migration drill. Local Git receive protection, not GitHub ruleset proof."""
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import git_state_anchor as g

sys.path.insert(0,str(g.q.ROOT/"ops"))
import asia_sources_connect as adapter

REF=g.REF
FLAGS=dict(release="HOLD",production_recommendations="DISABLED",deploymentAuthorized=False,
           githubProtectionVerified=False,providerCalls=0,classification="SYNTHETIC_ONLY")
def require(ok,reason):
    if not ok: raise ValueError(reason)
def fixture_bytes(offset):
    require(type(offset) is int and 0<=offset<=10000,"FIXTURE_OFFSET")
    stamp=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=offset)).isoformat()
    d=dict(schema=adapter.SCHEMA,collected_utc=stamp,status="RESEARCH_ONLY",model_inputs_changed=False,
           market_odds_changed=False,verified_betting_advantage=False,production_recommendations="DISABLED",
           open_meteo=dict(status="HOLD",requests_attempted=6,location_accuracy="CITY_CENTRE_PROXY_NOT_STADIUM",
                           upstream_issue_time_verified=False,attribution=adapter.ATTRIBUTION,license_url=adapter.LICENSE,
                           noncommercial_free_terms_apply=True,cities=[dict(city=k,display=n,latitude=lat,longitude=lon,status="NETWORK_UNAVAILABLE",samples=[]) for k,n,lat,lon in adapter.CITIES]),
           kleague=dict(status="NOT_CONFIGURED",configured=False,requests_attempted=0,league_count=0,
                        scope="AUTHORIZED_PARTNER_LEAGUE_CATALOGUE_ONLY",current_fixtures_verified=False,odds_available=False))
    return (json.dumps(d,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()
def unique(pairs):
    d={}
    for k,v in pairs:
        require(k not in d,"DUPLICATE_KEY")
        d[k]=v
    return d
def validate(raw):
    require(isinstance(raw,bytes) and len(raw)<=adapter.MAX_BYTES,"FIXTURE_SIZE")
    d=json.loads(raw,object_pairs_hook=unique)
    require(isinstance(d,dict),"FIXTURE_OBJECT")
    stamp=adapter.utc(d.get("collected_utc"))
    delta=(stamp-datetime(2026,1,1,tzinfo=timezone.utc)).total_seconds()
    require(delta.is_integer() and 0<=delta<=10000,"FIXTURE_TIME")
    expected=json.loads(fixture_bytes(int(delta)))
    require(json.dumps(d,sort_keys=True)==json.dumps(expected,sort_keys=True),"SYNTHETIC_SHAPE_ONLY")
    adapter.validate(d)
    return d
def digest(raw): return hashlib.sha256(raw).hexdigest()
def tip(store): return g.tip(store)
def read(store,commit):
    g.oid(commit)
    require(g.git(store,["ls-tree","--name-only",commit]).decode().splitlines()==["asia-fixture.json","manifest.json"],"TREE")
    raw=g.git(store,["show",commit+":asia-fixture.json"])
    d=validate(raw)
    m=json.loads(g.git(store,["show",commit+":manifest.json"]),object_pairs_hook=unique)
    p=g.git(store,["rev-list","--parents","-n","1",commit]).decode().split()
    require(p[0]==commit and len(p) in (1,2),"PARENT")
    parent=p[1] if len(p)==2 else None
    require(type(m.get("generation")) is int and 1<=m["generation"]<=32,"GENERATION")
    require(m==dict(schema="fk-asia-migration-v1",classification="SYNTHETIC_ONLY",release="HOLD",
                    production_recommendations="DISABLED",parent=parent,generation=m["generation"],
                    collected_utc=d["collected_utc"],sha256=digest(raw)),"MANIFEST")
    return dict(raw=raw,parent=parent,generation=m["generation"],collected_utc=d["collected_utc"],sha256=digest(raw))
def latest(store,expected):
    g.oid(expected)
    require(tip(store)==expected,"UNTRUSTED_TIP")
    head=read(store,expected);cur=head
    for _ in range(32):
        if cur["parent"] is None:
            require(cur["generation"]==1,"GENESIS");break
        prev=read(store,cur["parent"])
        require(prev["generation"]+1==cur["generation"] and adapter.utc(prev["collected_utc"])<adapter.utc(cur["collected_utc"]),"ROLLBACK")
        cur=prev
    else: raise ValueError("CHAIN_LIMIT")
    require(tip(store)==expected,"TIP_CHANGED")
    return head
def commit(store,parent,raw,gen):
    d=validate(raw);require(1<=gen<=32,"GENERATION")
    manifest=dict(schema="fk-asia-migration-v1",classification="SYNTHETIC_ONLY",release="HOLD",production_recommendations="DISABLED",
                  parent=parent,generation=gen,collected_utc=d["collected_utc"],sha256=digest(raw))
    blobs=[g.oid(g.git(store,["hash-object","-w","--stdin"],x).decode().strip()) for x in (raw,(json.dumps(manifest,sort_keys=True)+"\n").encode())]
    tree=g.oid(g.git(store,["mktree"],("100644 blob "+blobs[0]+"\tas ia-fixture.json\n100644 blob "+blobs[1]+"\tmanifest.json\n").replace("as ia","asia").encode()).decode().strip())
    return g.oid(g.git(store,["commit-tree",tree]+(["-p",parent] if parent else []),b"Synthetic Asia status only\n").decode().strip())
def init(remote,raw):
    g.init(remote)
    g.git(remote,["config","receive.denyNonFastForwards","true"])
    g.git(remote,["config","receive.denyDeletes","true"])
    x=commit(remote,None,raw,1)
    g.git(remote,["update-ref",REF,x,g.ZERO])
    latest(remote,x);return x
def clone(remote,dest):
    remote=g.outside(remote);dest=g.outside(dest)
    require(remote.is_dir() and not dest.exists(),"CLONE_PATH")
    g.invoke(["-c","protocol.file.allow=always","clone","--bare","--no-local",str(remote),str(dest)])
    return dest
def prepare(writer,expected,raw):
    old=latest(writer,expected);d=validate(raw)
    if old["raw"]==raw:return expected
    require(adapter.utc(d["collected_utc"])>adapter.utc(old["collected_utc"]),"STALE_OR_EQUAL_CONFLICT")
    return commit(writer,expected,raw,old["generation"]+1)
def push(writer,remote,new):
    g.oid(new)
    writer=g.outside(writer);remote=g.outside(remote)
    require(writer.parent==remote.parent and writer!=remote,"ISOLATION")
    try:
        g.git(writer,["-c","protocol.file.allow=always","push","--porcelain",str(remote),new+":"+REF])
        return True
    except RuntimeError:return False
def delete_drill(writer,remote):
    writer=g.outside(writer);remote=g.outside(remote)
    require(writer.parent==remote.parent and writer!=remote,"ISOLATION")
    try:
        g.git(writer,["-c","protocol.file.allow=always","push","--porcelain",str(remote),":"+REF])
        return True
    except RuntimeError:return False
def backup(store,expected,bundle):
    latest(store,expected);bundle=g.outside(bundle);require(not bundle.exists(),"BACKUP_EXISTS")
    g.git(store,["bundle","create",str(bundle),REF])
    require(bundle.stat().st_size<=g.MAX_BUNDLE,"BACKUP_LIMIT")
    require(g.invoke(["bundle","list-heads",str(bundle)]).decode().splitlines()==[expected+" "+REF],"BUNDLE_TIP")
    latest(store,expected)
def recover(bundle,dest,expected):
    bundle=g.outside(bundle);dest=g.outside(dest);g.oid(expected)
    require(bundle.is_file() and bundle.stat().st_size<=g.MAX_BUNDLE and not dest.exists(),"RECOVER_PATH")
    require(g.invoke(["bundle","list-heads",str(bundle)]).decode().splitlines()==[expected+" "+REF],"BUNDLE_TIP")
    g.invoke(["-c","protocol.file.allow=always","clone","--bare","--no-local",str(bundle),str(dest)])
    latest(dest,expected);return dest
def drill():
    with tempfile.TemporaryDirectory() as t:
        base=Path(t);remote=base/"remote.git";first=init(remote,fixture_bytes(0))
        w1=clone(remote,base/"writer1");w2=clone(remote,base/"writer2")
        raw=fixture_bytes(1);one=prepare(w1,first,raw);two=prepare(w2,first,fixture_bytes(2))
        require(push(w1,remote,one) and not push(w2,remote,two),"SIBLING")
        require(not delete_drill(w2,remote),"DELETE")
        bundle=base/"backup.bundle";backup(remote,one,bundle)
        restored=recover(bundle,base/"restored.git",one)
        out=latest(restored,one)
        require(out["raw"]==raw,"RAW_CHANGED")
        return dict(**FLAGS,status="ASIA_SYNTHETIC_MIGRATION_OK",generation=out["generation"],rawSha256=out["sha256"],
                    rawBytes=len(raw),bundleBytes=bundle.stat().st_size,localNonFastForwardRejected=True,localDeleteRejected=True,
                    rawBytesPreserved=True,restored=True)
if __name__=="__main__":
    if sys.argv[1:]!=["--drill"]:raise SystemExit(2)
    print(json.dumps(drill(),sort_keys=True))
