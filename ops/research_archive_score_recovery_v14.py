"""Read-only fixed-ID recovery of archived community final-score candidates.
Never changes the settled ledger or treats repeated snapshots as independent sources.
"""
import argparse
from collections import Counter, defaultdict
from datetime import timedelta
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
from .research_candidate_gap_v6 import audit, stamp
from .research_live_intake_v4 import decode, MAX_BYTES
from .team_identity import team_id

MAX_FILES=1500
MAX_COMPRESSED=1_000_000
NAME=re.compile(r"[0-9]{2}-[0-9]+\.json\.gz")

def targets(raw):
    if not audit(raw).get("structural_audit_passed"):
        raise ValueError("invalid candidate ledger")
    out={}
    for row in decode(raw)["samples"]:
        ident=row.get("source_fixture_identity")
        if not isinstance(ident,dict) or ident.get("provider")!="OpenLigaDB" or row["league"]!="bundesliga":
            continue
        match_id=ident.get("match_id")
        if not isinstance(match_id,str) or not re.fullmatch("[1-9][0-9]{0,19}",match_id) or match_id in out:
            raise ValueError("invalid or reused source ID")
        out[match_id]=row
    return out

def compare(raw, snapshots):
    """Snapshots are (archive label, uncompressed bytes); all remain untrusted."""
    wanted=targets(raw)
    found=defaultdict(list); conflicts=set(); rejected=0
    seen=set(); total=0
    for label,body in snapshots:
        total+=1
        if total>MAX_FILES:
            raise ValueError("archive budget exceeded")
        try:
            sha=hashlib.sha256(body).hexdigest()
            if sha in seen:
                continue
            seen.add(sha)
            doc=decode(body)
            if doc["schema"]!="football-king-openligadb-hourly-v1" or doc["source"]!="OpenLigaDB" or doc["production_recommendations"]!="DISABLED":
                raise ValueError("unexpected archive schema")
            captured=stamp(doc["collected_utc"])
            rows=doc["matches"]
            if not isinstance(rows,list) or len(rows)>100:
                raise ValueError("invalid archive rows")
            local=Counter(str(r.get("provider_match_id")) for r in rows if isinstance(r,dict))
            for r in rows:
                if not isinstance(r,dict):
                    continue
                ident=str(r.get("provider_match_id"))
                if ident not in wanted:
                    continue
                old=wanted[ident]; key=json.loads(old["key"]); ko=stamp(old["kickoff_utc"])
                try:
                    if type(r["provider_match_id"]) is not int or local[ident]!=1 or r["league"]!="bundesliga" or stamp(r["kickoff_utc"])!=ko or any(team_id("bundesliga",r[field])!=team_id("bundesliga",key[i]) for field,i in (("home",1),("away",2))):
                        conflicts.add(ident);continue
                    if r["status"]!="FINISHED_CONFIRMED_BY_SOURCE":
                        continue
                    score=r["score_ft"]
                    if not isinstance(score,list) or len(score)!=2 or any(type(v) is not int or not 0<=v<=30 for v in score) or captured<ko+timedelta(minutes=90):
                        conflicts.add(ident);continue
                    found[ident].append((tuple(score),label,sha,captured.isoformat()))
                except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
                    conflicts.add(ident)
        except (KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError):
            rejected+=1
    cases=[]
    for ident,row in sorted(wanted.items()):
        obs=found[ident]; scores={x[0] for x in obs}
        state="NO_ARCHIVED_FINAL_CANDIDATE"; score=None
        if ident in conflicts or len(scores)>1:
            state="CONFLICT_REVIEW"
        elif scores:
            score=list(next(iter(scores)));h,a=score
            state="SINGLE_PUBLISHER_OUTCOME_AGREEMENT" if (0 if h>a else 1 if h==a else 2)==row["y"] else "OUTCOME_CONFLICT_REVIEW"
        cases.append({"key":row["key"],"match_id":ident,"state":state,"score_candidate":score,
                      "observations":[{"path":x[1],"decoded_sha256":x[2],"captured_utc":x[3]} for x in obs],
                      "independently_verified":False})
    return {"schema":"fixed-id-archive-recovery-v14","status":"HOLD","production_recommendations":"DISABLED",
            "ledger_sha256":hashlib.sha256(raw).hexdigest(),"fixed_id_candidates":len(wanted),
            "snapshots_examined":total,"invalid_snapshots":rejected,"states":dict(Counter(x["state"] for x in cases)),
            "authenticated_samples":0,"independent_source_count":0,"scope":"SINGLE_COMMUNITY_PUBLISHER_ONLY",
            "regulation_result_independently_verified":False,"cases":cases}

def archive_snapshots(root, wanted):
    days=set()
    for row in wanted.values():
        day=stamp(row["kickoff_utc"]).date()
        days.update(day+timedelta(days=i) for i in range(4))
    count=0
    for day in sorted(days):
        folder=root/day.strftime("%Y/%m/%d")
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if not NAME.fullmatch(path.name) or not path.is_file() or path.is_symlink():
                continue
            count+=1
            if count>MAX_FILES:
                raise ValueError("archive budget exceeded")
            try:
                with path.open("rb") as stream:
                    compressed=stream.read(MAX_COMPRESSED+1)
                if len(compressed)>MAX_COMPRESSED:
                    raise ValueError("compressed budget")
                with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                    body=stream.read(MAX_BYTES+1)
                yield str(path.relative_to(root)),body
            except (OSError,EOFError,ValueError):
                yield str(path.relative_to(root)),b""

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",type=Path,default=Path("evidence/settled.json"))
    p.add_argument("--archive",type=Path,default=Path("sources/live_germany/history"))
    a=p.parse_args()
    with a.ledger.open("rb") as stream:raw=stream.read(MAX_BYTES+1)
    report=compare(raw,archive_snapshots(a.archive,targets(raw)))
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
