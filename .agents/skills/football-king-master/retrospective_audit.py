"""Offline pinned-ledger audit. Public score excerpts never certify forward evidence."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime

ROOT=Path(__file__).resolve().parents[3]
FILES=("retrospective-results-2026-11-28.json","retrospective-results-batch-2026-11-28.json")
PIN="dbe7fbdc007433792221113ae03295f349e5f84c"
COMMIT="739f24e709f0edf8c0cf75dfc9e0ff21e9c5bab7"
FALSE_FLAGS=("ledgerIndependentFlag","upstreamIndependenceVerified","rawSourceBytesCaptured","forecastSealAuthenticated","certifiedForwardCase")
def need(ok,reason):
    if not ok: raise ValueError(reason)
def unique(pairs):
    d={}
    for k,v in pairs:
        need(k not in d,"DUPLICATE_JSON_KEY");d[k]=v
    return d
def load(raw):
    need(isinstance(raw,bytes) and 0<len(raw)<=8*1024*1024,"INPUT_SIZE")
    return json.loads(raw,object_pairs_hook=unique)
def stamp(v):
    x=datetime.fromisoformat(v.replace("Z","+00:00"))
    need(x.tzinfo is not None,"NAIVE_TIME")
    return x
def audit(raw,docs):
    blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    need(blob==PIN,"PINNED_LEDGER_CHANGED")
    ledger=load(raw);rows=ledger["samples"]
    bykey={r["key"]:r for r in rows}
    need(len(rows)==len(bykey)==ledger["n"] and ledger["production_recommendations"]=="DISABLED","LEDGER")
    need(isinstance(docs,list) and 1<=len(docs)<=32,"BATCH_COUNT")
    seen=set();matched=0;per_league={}
    for doc in docs:
        need(doc["schema"]=="fk-retrospective-public-result-reconciliation-v1" and doc["classification"]=="RETROSPECTIVE_PUBLIC_WEB_RECONCILIATION_ONLY" and doc["release"]=="HOLD" and doc["production_recommendations"]=="DISABLED" and type(doc["certifiedForwardCases"]) is int and doc["certifiedForwardCases"]==0,"UNSAFE_EVIDENCE")
        need(doc["ledger"]==dict(commit=COMMIT,path="evidence/settled.json",blob=PIN,n=ledger["n"],checkedUtc=ledger["checked_utc"]),"LEDGER_BINDING")
        batch=doc["observations"];need(isinstance(batch,list) and len(batch)<=len(rows),"OBSERVATIONS")
        count=0
        for o in batch:
            key=o["key"];need(key in bykey and key not in seen,"UNKNOWN_OR_DUPLICATE_FIXTURE");seen.add(key)
            r=bykey[key];score=o["score"]
            need(isinstance(score,list) and len(score)==2 and all(type(v) is int and 0<=v<=30 for v in score),"SCORE")
            y=0 if score[0]>score[1] else 1 if score[0]==score[1] else 2
            need(type(o["ledgerOutcome"]) is int and type(o["scoreDerivedOutcome"]) is int and o["ledgerOutcome"]==r["y"] and o["scoreDerivedOutcome"]==y and o["ledgerOutcomeMatches"] is (y==r["y"]),"OUTCOME")
            need(all(o[k] is False for k in FALSE_FLAGS) and r["fixture_result_source_independently_verified"] is False,"FALSE_CERTIFICATION")
            for a,b in (("kickoffUtcFromLedger","kickoff_utc"),("forecastUtcFromLedger","forecast_utc"),("marketUtcFromLedger","market_utc")):
                need(o[a]==r[b],"TIME_BINDING")
            need(stamp(r["market_utc"])<=stamp(r["forecast_utc"])<stamp(r["kickoff_utc"])<stamp(ledger["checked_utc"]),"CHRONOLOGY")
            need(isinstance(o["sources"],list) and len(o["sources"])==2,"SOURCE_COUNT")
            names=set();domains=set()
            for s in o["sources"]:
                u=urlsplit(s["url"])
                need(u.scheme=="https" and u.hostname and not u.username and not u.password and isinstance(s["publisher"],str) and s["publisher"].strip(),"SOURCE_METADATA")
                names.add(s["publisher"].strip().casefold());domains.add(u.hostname.lower().removeprefix("www."))
            need(len(names)==len(domains)==2,"PUBLISHER_DUPLICATE")
            count+=int(y==r["y"]);per_league[r["league"]]=per_league.get(r["league"],0)+1
        need(type(doc["matchingOutcomes"]) is int and doc["matchingOutcomes"]==count,"COUNT_MISMATCH")
        matched+=count
    return dict(status="RETROSPECTIVE_AUDIT_OK",archived=len(rows),observed=len(seen),matching=matched,conflicting=len(seen)-matched,unreviewed=len(rows)-len(seen),certified=0,byLeague=per_league,sourceAuthenticityVerified=False,sourceUpstreamIndependenceVerified=False,forecastSealAuthenticated=False,release="HOLD",production_recommendations="DISABLED",deploymentAuthorized=False,providerCalls=0,ledgerSha256=hashlib.sha256(raw).hexdigest())
if __name__=="__main__":
    p=Path(__file__).parent
    print(json.dumps(audit((ROOT/"evidence/settled.json").read_bytes(),[load((p/f).read_bytes()) for f in FILES]),sort_keys=True))
