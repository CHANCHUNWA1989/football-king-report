"""Compare V14 recovered scores with a different archived publisher.
Cross-publisher agreement is not independent source authentication.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
from .research_archive_score_recovery_v14 import compare as primary_compare, targets, archive_snapshots
from .research_candidate_gap_v6 import stamp
from .research_live_intake_v4 import decode, MAX_BYTES
from .source_publish_guard import verify
from .team_identity import team_id

MAX_FILES=300
MAX_COMPRESSED=1_000_000

def secondary_snapshots(root, wanted):
    days={stamp(r["kickoff_utc"]).date()+timedelta(days=i)
          for r in wanted.values() for i in range(8)}
    n=0
    for day in sorted(days):
        folder=root/day.strftime("%Y/%m/%d")
        if not folder.is_dir() or folder.is_symlink():continue
        for path in sorted(folder.iterdir()):
            if not re.fullmatch(r"[0-9]+-[0-9]+\.json\.gz",path.name) or not path.is_file() or path.is_symlink():continue
            n+=1
            if n>MAX_FILES:raise ValueError("secondary archive budget")
            try:
                with path.open("rb") as f:packed=f.read(MAX_COMPRESSED+1)
                if len(packed)>MAX_COMPRESSED:raise ValueError("compressed limit")
                with gzip.GzipFile(fileobj=io.BytesIO(packed)) as f:body=f.read(MAX_BYTES+1)
                yield str(path.relative_to(root)),body
            except (OSError,EOFError,ValueError):yield str(path.relative_to(root)),b""

def crosscheck(raw, primary, secondary, *, as_of):
    wanted=targets(raw)
    first=primary_compare(raw,primary)
    now=stamp(as_of)
    def identity(league,home,away,kickoff):
        return (league,team_id(league,home),team_id(league,away),stamp(kickoff))
    lookup={}
    for mid,r in wanted.items():
        k=json.loads(r["key"])
        ident=identity(*k)
        if ident in lookup:raise ValueError("ambiguous ledger identity")
        lookup[ident]=mid
    found=defaultdict(list); collisions=set(); id_map=defaultdict(set)
    seen=set(); invalid=total=0
    for label,body in secondary:
        total+=1
        if total>MAX_FILES:raise ValueError("secondary archive budget")
        try:
            sha=hashlib.sha256(body).hexdigest()
            if sha in seen:continue
            seen.add(sha)
            doc=decode(body); captured=verify(doc,now=now)
            if captured>now:raise ValueError("future snapshot")
            local=defaultdict(list)
            for row in doc["sampled_fixtures"]:
                if row["provider"]!="thesportsdb" or row["league"]!="bundesliga":continue
                ident=identity(row["league"],row["home"],row["away"],row["kickoff_utc"])
                sid=row["provider_event_id"]
                id_map[sid].add(ident)
                if ident not in lookup:continue
                mid=lookup[ident]
                local[mid].append(row)
            for mid,rows in local.items():
                if len(rows)!=1:
                    collisions.add(mid);continue
                r=rows[0]
                if r["status"]!="FINISHED" or r["score_ft"] is None:continue
                ko=stamp(r["kickoff_utc"])
                if captured<ko+timedelta(minutes=90):
                    collisions.add(mid);continue
                found[mid].append((tuple(r["score_ft"]),r["provider_event_id"],label,sha))
        except (KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError):
            invalid+=1
    cases=[]
    for p in first["cases"]:
        mid=p["match_id"]; obs=found[mid]; scores={x[0] for x in obs}; ids={x[1] for x in obs}
        state="NO_SECOND_PUBLISHER_FINAL"
        if p["state"]!="SINGLE_PUBLISHER_OUTCOME_AGREEMENT":
            state="PRIMARY_UNRESOLVED"
        elif mid in collisions or len(scores)>1 or len(ids)>1 or any(len(id_map[x])!=1 for x in ids):
            state="SECONDARY_CONFLICT_REVIEW"
        elif scores:
            state="TWO_PUBLISHER_EXACT_SCORE_CANDIDATE" if tuple(p["score_candidate"]) in scores else "CROSS_PUBLISHER_SCORE_CONFLICT"
        cases.append({"match_id":mid,"state":state,"primary_score":p["score_candidate"],
                      "secondary_scores":[list(x) for x in sorted(scores)],
                      "secondary_observations":[{"provider_event_id":x[1],"path":x[2],"decoded_sha256":x[3]} for x in obs],
                      "independently_verified":False})
    return {"schema":"two-publisher-archive-recovery-v15","status":"HOLD","production_recommendations":"DISABLED",
            "fixed_id_candidates":len(wanted),"primary_snapshots_examined":first["snapshots_examined"],
            "secondary_snapshots_examined":total,"invalid_secondary_snapshots":invalid,
            "states":dict(Counter(x["state"] for x in cases)),"authenticated_samples":0,
            "upstream_independence_proven":False,"regulation_result_independently_verified":False,
            "forecast_witness_verified":False,"cases":cases}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    a=p.parse_args()
    with (a.root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    wanted=targets(raw)
    r=crosscheck(raw,archive_snapshots(a.root/"sources/live_germany/history",wanted),
                 secondary_snapshots(a.root/"sources/history",wanted),as_of=datetime.now(timezone.utc).isoformat())
    print(json.dumps(r,sort_keys=True,allow_nan=False))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
