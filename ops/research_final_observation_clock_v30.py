"""Recover conservative final-observation clocks from the same original archives.

Recorded archive capture time is a research candidate, not authenticated publication
time, actual finish time or proof of availability to a historical model.
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
from .research_historical_evidence_triage_v17 import bounded
from .research_german_archive_discovery_v18 import extend
from .source_publish_guard import verify

AGREEMENTS={"ONE_PUBLISHER_OUTCOME_AGREEMENT","TWO_PUBLISHER_SCORE_AGREEMENT"}

def recover(raw,primary,secondary,*,as_of):
    now=stamp(as_of);rows=candidates(raw)
    first=bounded(primary,PRIMARY_MAX,now,"collected_utc")
    second=bounded(secondary,SECONDARY_MAX,now,"collected_utc")
    prior=extend(raw,first,second,as_of=now.isoformat())
    expected={r["key"]:r for r in prior["cases"]}
    wanted={k:r for k,r in rows.items() if expected[r["key"]]["state"] in AGREEMENTS}
    refs=defaultdict(set)
    for k,r in wanted.items():
        for ref in expected[r["key"]]["references"]:
            refs[(ref["provider"],ref["path"],ref["decoded_sha256"])].add(k)
    found=defaultdict(lambda:defaultdict(list))
    invalid=Counter()
    for provider,stream in (("OpenLigaDB",first),("thesportsdb",second)):
        for path,body in stream:
            sha=hashlib.sha256(body).hexdigest()
            allowed=refs.get((provider,path,sha))
            if not allowed:continue
            try:
                doc=decode(body)
                if provider=="OpenLigaDB":
                    if (doc["schema"]!="football-king-openligadb-hourly-v1"
                        or doc["source"]!=provider or doc["production_recommendations"]!="DISABLED"
                        or not isinstance(doc["matches"],list) or len(doc["matches"])>100):
                        raise ValueError("invalid primary")
                    captured=stamp(doc["collected_utc"]);records=doc["matches"]
                    finished="FINISHED_CONFIRMED_BY_SOURCE";id_field="provider_match_id"
                else:
                    captured=verify(doc,now=now)
                    records=[r for r in doc["sampled_fixtures"] if r["provider"]==provider]
                    finished="FINISHED";id_field="provider_event_id"
                if captured>now:raise ValueError("future observation")
                staged=defaultdict(list)
                for r in records:
                    k=identity(r["league"],r["home"],r["away"],r["kickoff_utc"])
                    if k in allowed:staged[k].append(r)
                for k,rs in staged.items():
                    if len(rs)!=1:raise ValueError("ambiguous local fixture")
                    r=rs[0]
                    if r["status"]!=finished or r["score_ft"] is None:continue
                    score=r["score_ft"];sid=r[id_field]
                    if (not isinstance(score,list) or len(score)!=2
                        or any(type(v) is not int or not 0<=v<=30 for v in score)
                        or captured<k[3]+timedelta(minutes=90)):
                        raise ValueError("invalid final observation")
                    if provider=="OpenLigaDB" and (type(sid) is not int or sid<=0):
                        raise ValueError("invalid primary ID")
                    if provider=="thesportsdb" and (not isinstance(sid,str) or not sid):
                        raise ValueError("invalid secondary ID")
                    if (0 if score[0]>score[1] else 1 if score[0]==score[1] else 2)!=wanted[k]["y"]:
                        raise ValueError("outcome conflict")
                # Commit only after all relevant rows have passed.
                for k,rs in staged.items():
                    r=rs[0]
                    if r["status"]==finished and r["score_ft"] is not None:
                        found[k][provider].append((captured,tuple(r["score_ft"]),str(r[id_field]),path,sha))
            except (KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError):
                invalid[provider]+=1
    cases=[]
    for k,r in sorted(rows.items()):
        state=expected[r["key"]]["state"]
        case={"key":r["key"],"result_state":state,"state":"NO_ELIGIBLE_FINAL_CLOCK",
              "recorded_final_observation_utc":None,"references":[],
              "result_availability_authenticated":False,"training_admission":False}
        if k in wanted:
            obs=found[k]
            scores={x[1] for values in obs.values() for x in values}
            if len(scores)>1 or any(len({x[2] for x in values})!=1 for values in obs.values()):
                case["state"]="FINAL_CLOCK_CONFLICT"
            elif obs and (state!="TWO_PUBLISHER_SCORE_AGREEMENT" or len(obs)==2):
                earliest={p:min(values) for p,values in obs.items()}
                # For dual agreement wait for both recorded final observations.
                clock=max(x[0] for x in earliest.values())
                case.update(state="TWO_PUBLISHER_FINAL_CLOCK_CANDIDATE" if len(earliest)==2 else "SINGLE_PUBLISHER_FINAL_CLOCK_CANDIDATE",
                    recorded_final_observation_utc=clock.isoformat(),score_candidate=list(next(iter(scores))),
                    references=[{"provider":p,"captured_utc":x[0].isoformat(),"provider_id":x[2],
                       "path":x[3],"decoded_sha256":x[4]} for p,x in sorted(earliest.items())])
        cases.append(case)
    return {"schema":"recorded-final-observation-clock-v30","status":"HOLD",
            "production_recommendations":"DISABLED","ledger_sha256":hashlib.sha256(raw).hexdigest(),
            "ledger_rows":len(rows),"states":dict(Counter(x["state"] for x in cases)),
            "invalid_referenced_snapshots":dict(invalid),"authenticated_samples":0,
            "training_admission":False,"actual_publication_time_authenticated":False,
            "model_promotion_allowed":False,"cases":cases}

def from_root(root,*,as_of):
    with (root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    rows=candidates(raw)
    return recover(raw,archive_snapshots(root/"sources/live_germany/history",{k:r for k,r in rows.items() if k[0]=="bundesliga"}),
                   secondary_snapshots(root/"sources/history",rows),as_of=as_of)
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path("."))
    a=p.parse_args()
    print(json.dumps(from_root(a.root,as_of=datetime.now(timezone.utc).isoformat()),sort_keys=True,allow_nan=False))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
