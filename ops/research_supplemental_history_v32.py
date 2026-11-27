"""Discover extra, unsealed history in existing bounded result archives.

No retrospective forecast, authentication, model fitting or test admission.
"""
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
from .research_candidate_gap_v6 import stamp
from .research_missing_fixture_discovery_v16 import candidates,identity
from .research_live_intake_v4 import decode,MAX_BYTES
from .research_archive_score_recovery_v14 import archive_snapshots,MAX_FILES as PRIMARY_MAX
from .research_two_publisher_recovery_v15 import secondary_snapshots,MAX_FILES as SECONDARY_MAX
from .research_historical_evidence_triage_v17 import bounded
from .research_final_observation_clock_v30 import recover
from .source_publish_guard import verify

def inventory(raw,primary,secondary,*,as_of):
    now=stamp(as_of);rows=candidates(raw)
    first=bounded(primary,PRIMARY_MAX,now,"collected_utc")
    second=bounded(secondary,SECONDARY_MAX,now,"collected_utc")
    old=recover(raw,first,second,as_of=now.isoformat())
    ledger_pairs={k[:3] for k in rows}
    teams={(k[0],t) for k in rows for t in k[1:3]}
    ids=defaultdict(set);fixture_ids=defaultdict(set)
    observations=defaultdict(list);pair_kickoffs=defaultdict(set)
    conflicts=set();invalid=Counter()
    for provider,stream in (("OpenLigaDB",first),("thesportsdb",second)):
        seen=set()
        for path,body in stream:
            try:
                sha=hashlib.sha256(body).hexdigest()
                if sha in seen:continue
                doc=decode(body)
                if provider=="OpenLigaDB":
                    if (doc["schema"]!="football-king-openligadb-hourly-v1" or doc["source"]!=provider
                        or doc["production_recommendations"]!="DISABLED"
                        or not isinstance(doc["matches"],list) or len(doc["matches"])>100):
                        raise ValueError("invalid primary archive")
                    captured=stamp(doc["collected_utc"]);records=doc["matches"]
                    finished="FINISHED_CONFIRMED_BY_SOURCE";id_field="provider_match_id"
                else:
                    captured=verify(doc,now=now)
                    records=[r for r in doc["sampled_fixtures"] if r["provider"]==provider]
                    finished="FINISHED";id_field="provider_event_id"
                if captured>now:raise ValueError("future archive")
                staged=[]
                for r in records:
                    if provider=="OpenLigaDB" and r["league"]!="bundesliga":continue
                    k=identity(r["league"],r["home"],r["away"],r["kickoff_utc"])
                    sid=r[id_field]
                    if provider=="OpenLigaDB" and (type(sid) is not int or sid<=0):
                        raise ValueError("invalid primary ID")
                    if provider=="thesportsdb" and (not isinstance(sid,str) or not sid.strip()):
                        raise ValueError("invalid secondary ID")
                    score=None
                    if r["status"]==finished and r["score_ft"] is not None:
                        s=r["score_ft"]
                        if (not isinstance(s,list) or len(s)!=2
                            or any(type(v) is not int or not 0<=v<=30 for v in s)
                            or captured<k[3]+timedelta(minutes=90)):
                            raise ValueError("invalid final")
                        score=tuple(s)
                    staged.append((k,str(sid),score))
                seen.add(sha)
                local=Counter(k for k,_,_ in staged)
                for k,sid,score in staged:
                    ids[(provider,sid)].add(k)
                    fixture_ids[(provider,k)].add(sid)
                    pair_kickoffs[k[:3]].add(k[3])
                    if local[k]>1:conflicts.add(k)
                    if score is not None:
                        observations[k].append((provider,captured,score,sid,path,sha))
            except (KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError):
                invalid[provider]+=1
    excluded=Counter();extra=[]
    earliest_forecast=min(stamp(r["forecast_utc"]) for r in rows.values())
    latest_forecast=max(stamp(r["forecast_utc"]) for r in rows.values())
    for k,obs in sorted(observations.items()):
        if k[:3] in ledger_pairs:
            excluded["LEDGER_PAIR_OR_POSSIBLE_RESCHEDULE"]+=1;continue
        if not any((k[0],t) in teams for t in k[1:3]):
            excluded["UNRELATED_TEAM"]+=1;continue
        if not earliest_forecast-timedelta(days=90)<=k[3]<latest_forecast:
            excluded["OUTSIDE_RESEARCH_WINDOW"]+=1;continue
        if (k in conflicts or len(pair_kickoffs[k[:3]])!=1
            or len({x[2] for x in obs})!=1
            or any(len(ids[(p,sid)])!=1 or len(fixture_ids[(p,k)])!=1 for p,_,_,sid,_,_ in obs)):
            excluded["IDENTITY_OR_SCORE_CONFLICT"]+=1;continue
        first_by={}
        for o in obs:
            p=o[0]
            if p not in first_by or o[1:]<first_by[p][1:]:first_by[p]=o
        clock=max(x[1] for x in first_by.values())
        if clock>=latest_forecast:
            excluded["NO_PRIOR_FORECAST_USE"]+=1;continue
        extra.append((clock,k,len(first_by),next(iter({x[2] for x in obs}))))
    by_key={r["key"]:k for k,r in rows.items()}
    base=[(stamp(c["recorded_final_observation_utc"]),by_key[c["key"]])
          for c in old["cases"] if c["recorded_final_observation_utc"] is not None]
    target=[(stamp(rows[k]["forecast_utc"]),k) for _,k in base
            if stamp(rows[k]["forecast_utc"])<=k[3]-timedelta(minutes=10)]
    def counts(pool,delay):
        queue=sorted((t+timedelta(hours=delay),k) for t,k in pool)
        i=0;leagues=Counter();team=Counter();result=Counter()
        for f,k in sorted(target):
            while i<len(queue) and queue[i][0]<f:
                _,p=queue[i];i+=1
                leagues[p[0]]+=1
                for name in p[1:3]:team[(p[0],name)]+=1
            both=min(team[(k[0],k[1])],team[(k[0],k[2])])
            result["both_teams_at_least_3_prior"]+=int(both>=3)
            result["all_three_thresholds"]+=int(i>=30 and leagues[k[0]]>=5 and both>=3)
        return dict(result)
    return {"schema":"supplemental-history-inventory-v32","status":"HOLD",
            "production_recommendations":"DISABLED","ledger_sha256":hashlib.sha256(raw).hexdigest(),
            "ledger_rows":len(rows),"extra_prior_candidates":len(extra),
            "extra_dual_candidates":sum(n==2 for _,_,n,_ in extra),
            "extra_by_league":dict(Counter(k[0] for _,k,_,_ in extra)),
            "excluded":dict(excluded),"invalid_snapshots":dict(invalid),
            "forecast_target_count":len(target),
            "scenarios":{str(d):{"original":counts(base,d),
                "expanded":counts(base+[(t,k) for t,k,_,_ in extra],d)} for d in (0,6,24)},
            "authenticated_samples":0,"archive_timestamps_authenticated":False,
            "training_admission":False,"model_promotion_allowed":False,
            "weights_fitted":False,"selection_bias_possible":True}

def from_root(root,*,as_of):
    with (root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    rows=candidates(raw)
    return inventory(raw,archive_snapshots(root/"sources/live_germany/history",
        {k:r for k,r in rows.items() if k[0]=="bundesliga"}),
        secondary_snapshots(root/"sources/history",rows),as_of=as_of)
