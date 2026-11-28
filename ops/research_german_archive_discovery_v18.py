"""Read-only OpenLigaDB identity discovery for previously unpinned Bundesliga rows.
Extends V17 without modifying the original ledger or claiming independence.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
from .research_live_intake_v4 import decode,MAX_BYTES
from .research_candidate_gap_v6 import stamp
from .research_missing_fixture_discovery_v16 import candidates,identity
from .research_archive_score_recovery_v14 import archive_snapshots,MAX_FILES as PRIMARY_MAX
from .research_two_publisher_recovery_v15 import secondary_snapshots,MAX_FILES as SECONDARY_MAX
from .research_historical_evidence_triage_v17 import review,bounded

def extend(raw,primary,secondary,*,as_of):
    now=stamp(as_of)
    rows=candidates(raw)
    wanted={k:r for k,r in rows.items() if k[0]=="bundesliga" and not r.get("source_fixture_identity")}
    first=bounded(primary,PRIMARY_MAX,now,"collected_utc")
    second=bounded(secondary,SECONDARY_MAX,now,"collected_utc")
    result=review(raw,first,second,as_of=now.isoformat())
    ids=defaultdict(set); matches=defaultdict(set); scores=defaultdict(set)
    refs=defaultdict(set); conflicts=set(); seen=set(); invalid=0
    # Existing pinned IDs cannot be rediscovered for another fixture.
    for k,r in rows.items():
        ident=r.get("source_fixture_identity")
        if isinstance(ident,dict) and ident.get("provider")=="OpenLigaDB":
            ids[ident["match_id"]].add(k)
    for label,body in first:
        try:
            sha=hashlib.sha256(body).hexdigest()
            if sha in seen:continue
            doc=decode(body)
            if doc["schema"]!="football-king-openligadb-hourly-v1" or doc["source"]!="OpenLigaDB" or doc["production_recommendations"]!="DISABLED":
                raise ValueError("unexpected primary schema")
            t=stamp(doc["collected_utc"])
            if t>now:raise ValueError("future snapshot")
            records=doc["matches"]
            if not isinstance(records,list) or len(records)>100:raise ValueError("bad rows")
            staged=[]
            for r in records:
                if not isinstance(r,dict):raise ValueError("invalid row")
                if r["league"]!="bundesliga":continue
                mid=r["provider_match_id"]
                if type(mid) is not int or mid<=0:raise ValueError("invalid ID")
                k=identity(r["league"],r["home"],r["away"],r["kickoff_utc"])
                score=None
                if r["status"]=="FINISHED_CONFIRMED_BY_SOURCE":
                    value=r["score_ft"]
                    if not isinstance(value,list) or len(value)!=2 or any(type(v) is not int or not 0<=v<=30 for v in value):
                        raise ValueError("bad final")
                    score=tuple(value)
                staged.append((k,str(mid),score))
            seen.add(sha)
            local=Counter(k for k,_,_ in staged)
            for k,mid,score in staged:
                ids[mid].add(k)
                if k not in wanted:continue
                matches[k].add(mid)
                refs[k].add((label,sha,t.isoformat()))
                if local[k]>1:conflicts.add(k)
                if score is not None:
                    if t<k[3]+timedelta(minutes=90):conflicts.add(k)
                    else:scores[k].add(score)
        except (KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError):
            invalid+=1
    by_key={x["key"]:x for x in result["cases"]}
    discovery=Counter()
    for k,r in wanted.items():
        case=by_key[r["key"]]
        m=matches[k];s=scores[k]
        state="NO_EXACT_PRIMARY_MATCH"
        if k in conflicts or len(m)>1 or len(s)>1 or any(len(ids[x])!=1 for x in m):
            state="PRIMARY_CONFLICT_REVIEW"
        elif m:
            state="PRIMARY_ID_CANDIDATE"
            if s:
                h,a=next(iter(s))
                state="PRIMARY_OUTCOME_CANDIDATE" if (0 if h>a else 1 if h==a else 2)==r["y"] else "PRIMARY_OUTCOME_CONFLICT"
        discovery[state]+=1
        detail={"state":state,"candidate_ids":sorted(m),"candidate_scores":[list(x) for x in sorted(s)],
                "references":[{"provider":"OpenLigaDB","path":p,"decoded_sha256":d,"captured_utc":t} for p,d,t in sorted(refs[k])],
                "identity_discovered_posthoc":True}
        case["primary_discovery_candidate"]=detail
        case["references"].extend(detail["references"])
        prior=case["state"]
        if "CONFLICT" in state or prior=="CONFLICT_REVIEW":
            case["state"]="CONFLICT_REVIEW"
        elif state=="PRIMARY_OUTCOME_CANDIDATE":
            other=case.get("discovery_candidate") or {}
            if other.get("state")=="FIXTURE_AND_OUTCOME_CANDIDATE":
                case["state"]="TWO_PUBLISHER_SCORE_AGREEMENT" if next(iter(s)) in {tuple(x) for x in other["candidate_scores"]} else "CONFLICT_REVIEW"
            else:case["state"]="ONE_PUBLISHER_OUTCOME_AGREEMENT"
        elif state=="PRIMARY_ID_CANDIDATE" and prior=="NO_EXACT_FIXTURE_MATCH":
            case["state"]="IDENTITY_ONLY"
        if case["state"]!=prior:
            blockers=["INDEPENDENT_FORECAST_WITNESS_MISSING","AUTHENTICATED_REGULATION_RESULT_MISSING","SOURCE_UPSTREAM_INDEPENDENCE_UNPROVEN"]
            specific={"CONFLICT_REVIEW":"RESOLVE_IDENTITY_OR_SCORE_CONFLICT",
                      "IDENTITY_ONLY":"RECOVER_FINAL_SCORE",
                      "ONE_PUBLISHER_OUTCOME_AGREEMENT":"RECOVER_SECOND_PUBLISHER_SCORE"}
            if case["state"] in specific:blockers.insert(0,specific[case["state"]])
            case["blockers"]=blockers
    states=dict(Counter(x["state"] for x in result["cases"]))
    result.update(schema="unified-historical-evidence-v18",states=states,
        outcome_corroborated_candidates=states.get("ONE_PUBLISHER_OUTCOME_AGREEMENT",0)+states.get("TWO_PUBLISHER_SCORE_AGREEMENT",0),
        blocker_counts=dict(Counter(b for x in result["cases"] for b in x["blockers"])),
        primary_discovery_targets=len(wanted),primary_discovery_states=dict(discovery),
        primary_discovery_invalid_snapshots=invalid,authenticated_samples=0,
        ledger_backfill_allowed=False)
    return result

def from_root(root,*,as_of):
    with (root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    rows=candidates(raw)
    german={k:r for k,r in rows.items() if k[0]=="bundesliga"}
    return extend(raw,archive_snapshots(root/"sources/live_germany/history",german),
                  secondary_snapshots(root/"sources/history",rows),as_of=as_of)

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path("."))
    a=p.parse_args()
    print(json.dumps(from_root(a.root,as_of=datetime.now(timezone.utc).isoformat()),sort_keys=True,allow_nan=False))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
