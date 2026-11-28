"""Discover missing provider IDs in existing historical sanitized reports.
Exact league/team/time matching only. Never backfill immutable ledger identity.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
from .research_candidate_gap_v6 import audit,stamp
from .research_live_intake_v4 import decode,MAX_BYTES
from .research_two_publisher_recovery_v15 import secondary_snapshots,MAX_FILES
from .source_publish_guard import verify
from .team_identity import team_id

def identity(league,home,away,kickoff):
    h,a=team_id(league,home),team_id(league,away)
    if not h or not a or h==a:
        raise ValueError("ambiguous team identity")
    return league,h,a,stamp(kickoff)

def candidates(raw):
    if not audit(raw).get("structural_audit_passed"):
        raise ValueError("unsafe candidate ledger")
    result={}
    for row in decode(raw)["samples"]:
        key=identity(*json.loads(row["key"]))
        if key in result:
            raise ValueError("canonical alias collision")
        result[key]=row
    return result

def discover(raw,snapshots,*,as_of):
    rows=candidates(raw)
    missing={k:r for k,r in rows.items() if not r.get("source_fixture_identity")}
    now=stamp(as_of)
    ids=defaultdict(set); fixtures=defaultdict(set); finals=defaultdict(set)
    refs=defaultdict(set); conflicts=set(); seen=set()
    total=invalid=0
    for label,body in snapshots:
        total+=1
        if total>MAX_FILES:raise ValueError("archive budget exceeded")
        try:
            sha=hashlib.sha256(body).hexdigest()
            if sha in seen:continue
            doc=decode(body);t=verify(doc,now=now)
            if t>now:raise ValueError("future archive")
            # Stage the entire snapshot before changing any cross-file indexes.
            staged=[]
            for r in doc["sampled_fixtures"]:
                if r["provider"]!="thesportsdb":continue
                k=identity(r["league"],r["home"],r["away"],r["kickoff_utc"])
                sid=r["provider_event_id"]
                score=tuple(r["score_ft"]) if r["status"]=="FINISHED" and r["score_ft"] is not None else None
                staged.append((k,sid,score))
            seen.add(sha)
            local=Counter(k for k,_,_ in staged)
            for k,sid,score in staged:
                ids[sid].add(k)
                if k not in missing:continue
                fixtures[k].add(sid)
                if local[k]>1:conflicts.add(k)
                refs[k].add((label,sha,t.isoformat()))
                if score is not None:
                    if t<k[3]+timedelta(minutes=90):conflicts.add(k)
                    else:finals[k].add(score)
        except (KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError):
            invalid+=1
    cases=[]
    for k,r in sorted(missing.items()):
        s=fixtures[k];scores=finals[k];state="NO_EXACT_FIXTURE_MATCH"
        if k in conflicts or len(s)>1 or len(scores)>1 or any(len(ids[x])!=1 for x in s):
            state="AMBIGUOUS_OR_CONFLICTING"
        elif s:
            state="FIXTURE_ID_CANDIDATE_ONLY"
            if scores:
                h,a=next(iter(scores))
                state="FIXTURE_AND_OUTCOME_CANDIDATE" if (0 if h>a else 1 if h==a else 2)==r["y"] else "RECORDED_OUTCOME_CONFLICT"
        cases.append({"key":r["key"],"league":k[0],"state":state,"provider":"thesportsdb",
                      "candidate_ids":sorted(s),"candidate_scores":[list(x) for x in sorted(scores)],
                      "snapshot_references":[{"path":p,"decoded_sha256":d,"captured_utc":t} for p,d,t in sorted(refs[k])],
                      "independently_verified":False,"ledger_backfill_allowed":False})
    return {"schema":"missing-fixture-id-discovery-v16","status":"HOLD","production_recommendations":"DISABLED",
            "ledger_sha256":hashlib.sha256(raw).hexdigest(),"ledger_rows":len(rows),"missing_identity_rows":len(missing),
            "snapshots_examined":total,"invalid_snapshots":invalid,"states":dict(Counter(x["state"] for x in cases)),
            "by_league":{l:dict(Counter(x["state"] for x in cases if x["league"]==l)) for l in sorted({x["league"] for x in cases})},
            "authenticated_samples":0,"forecast_witness_verified":False,"ledger_backfill_allowed":False,"cases":cases}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    a=p.parse_args()
    with (a.root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    rows=candidates(raw);wanted={k:r for k,r in rows.items() if not r.get("source_fixture_identity")}
    report=discover(raw,secondary_snapshots(a.root/"sources/history",wanted),as_of=datetime.now(timezone.utc).isoformat())
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
