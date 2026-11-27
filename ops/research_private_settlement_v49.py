"""Private settlement candidates for V48 runs, without changing forecasts.

Use original sanitized OpenLigaDB and TheSportsDB snapshot bytes. Agreement
between publishers does not prove upstream independence, actual kickoff,
regulation-time score or external forecast timing. No network or writes.
"""
from collections import Counter,defaultdict
from datetime import timedelta
import json
from .research_private_run_store_v48 import verify_run,unb64
from .research_live_intake_v4 import decode
from .research_prospective_fusion_v38 import sha,token
from .research_missing_fixture_discovery_v16 import identity
from .research_candidate_gap_v6 import stamp
from .research_archive_score_recovery_v14 import MAX_FILES as PRIMARY_MAX
from .research_two_publisher_recovery_v15 import MAX_FILES as SECONDARY_MAX
from .source_publish_guard import verify

def settle(run_raw,primary,secondary,*,as_of):
    audit=verify_run(run_raw);now=stamp(as_of)
    d=json.loads(run_raw)
    if stamp(d["forecast_utc"])>now:raise ValueError("future forecast")
    targets={}
    for packet in d["packets"]:
        doc=decode(unb64(packet["raw_input"]))
        k=identity(doc["league"],doc["home"],doc["away"],doc["kickoff_utc"])
        if k in targets:raise ValueError("duplicate target")
        targets[k]=packet["receipt"]
    observations=defaultdict(lambda:defaultdict(list))
    ids=defaultdict(set);fixture_ids=defaultdict(set)
    pair_dates=defaultdict(set);conflicts=set();counts=Counter()
    target_pairs={k[:3] for k in targets}
    for provider,stream,limit in (("OpenLigaDB",primary,PRIMARY_MAX),("thesportsdb",secondary,SECONDARY_MAX)):
        seen=set()
        for i,(path,body) in enumerate(stream):
            if i>=limit:raise ValueError("archive budget exceeded")
            digest=sha(body)
            if digest in seen:continue
            doc=decode(body)
            if provider=="OpenLigaDB":
                if (doc["schema"]!="football-king-openligadb-hourly-v1"
                    or doc["source"]!=provider or doc["production_recommendations"]!="DISABLED"
                    or not isinstance(doc["matches"],list) or len(doc["matches"])>100):
                    raise ValueError("invalid primary snapshot")
                t=stamp(doc["collected_utc"]);records=doc["matches"]
                field="provider_match_id";finished="FINISHED_CONFIRMED_BY_SOURCE"
            else:
                t=verify(doc,now=now)
                records=[r for r in doc["sampled_fixtures"] if r["provider"]==provider]
                field="provider_event_id";finished="FINISHED"
            if t>now:raise ValueError("future result snapshot")
            seen.add(digest);counts[provider]+=1
            local=Counter()
            for r in records:
                if provider=="OpenLigaDB" and r["league"]!="bundesliga":continue
                k=identity(r["league"],r["home"],r["away"],r["kickoff_utc"])
                sid=r[field]
                if provider=="OpenLigaDB" and (type(sid) is not int or sid<=0):
                    raise ValueError("invalid primary ID")
                sid=token(str(sid))
                ids[(provider,sid)].add(k);fixture_ids[(provider,k)].add(sid)
                if k[:3] in target_pairs:pair_dates[k[:3]].add(k[3])
                if k not in targets:continue
                local[k]+=1
                if r["status"]!=finished or r.get("score_ft") is None:continue
                s=r["score_ft"]
                if (not isinstance(s,list) or len(s)!=2 or any(type(v) is not int or not 0<=v<=30 for v in s)
                    or t<k[3]+timedelta(minutes=90)):
                    conflicts.add(k);continue
                observations[k][provider].append((t,tuple(s),sid,path,digest))
            conflicts.update(k for k,n in local.items() if n!=1)
    cases=[];states=Counter()
    for k,receipt in sorted(targets.items()):
        obs=observations[k]
        scores={v[1] for group in obs.values() for v in group}
        state="NO_FINAL_SCORE";score=None;refs=[]
        if now<k[3]+timedelta(minutes=90):
            state="AWAITING_FINAL_WINDOW"
        elif (k in conflicts or any(x!=k[3] for x in pair_dates[k[:3]])
              or len(scores)>1
              or any(len(ids[(p,v[2])])!=1 or len(fixture_ids[(p,k)])!=1
                     for p,group in obs.items() for v in group)):
            state="RESULT_CONFLICT_REVIEW"
        elif len(obs)==2:
            state="TWO_PUBLISHER_SCORE_CANDIDATE"
            score=list(next(iter(scores)))
            refs=[{"provider":p,"captured_utc":v[0].isoformat(),"provider_id":v[2],
                   "path":v[3],"decoded_sha256":v[4]}
                  for p,group in sorted(obs.items()) for v in [min(group)]]
        elif len(obs)==1:
            state="SINGLE_PUBLISHER_REVIEW"
        states[state]+=1
        cases.append({"fixture":[*k[:3],k[3].isoformat()],
                      "receipt_sha256":receipt["receipt_sha256"],"state":state,
                      "score_candidate":score,"references":refs,
                      "outcome_candidate":None if score is None else (0 if score[0]>score[1] else 1 if score[0]==score[1] else 2),
                      "independently_verified":False,"training_admission":False})
    report={"schema":"private-fusion-settlement-v49","status":"HOLD",
            "run_sha256":audit["run_sha256"],"forecast_count":len(targets),
            "states":dict(states),"snapshots_examined":dict(counts),
            "two_publisher_candidates":states["TWO_PUBLISHER_SCORE_CANDIDATE"],
            "external_forecast_witness_verified":False,"actual_kickoff_authenticated":False,
            "regulation_score_authenticated":False,"upstream_independence_proven":False,
            "authenticated_samples":0,"training_admission":False,"publication_allowed":False,
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
    return cases,report
