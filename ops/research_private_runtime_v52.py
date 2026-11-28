"""V52: private operator entry for capture and replayed cohort evaluation.

No network in review mode. Collection is explicit, authorized, quota bounded,
and requires a persistent private store. Never publish raw data or enable tips.
A local digest roster does not authenticate sources or prove cohort completeness.
"""
import argparse
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from .research_private_acquisition_v47 import pilot, SPORTS
from .research_private_run_store_v48 import root_fd, MAX_RUN_BYTES
from .research_private_evaluation_v50 import evaluate, MAX_RUNS, MAX_COHORT_BYTES
from .research_live_intake_v4 import MAX_BYTES
from .research_archive_score_recovery_v14 import MAX_FILES as PRIMARY_MAX
from .research_two_publisher_recovery_v15 import MAX_FILES as SECONDARY_MAX
from .research_prospective_fusion_v38 import sha, fingerprint
from .research_candidate_gap_v6 import stamp

MAX_RESULT_BYTES=128*1024*1024

def safety():
    return {"schema":"private-runtime-v52","status":"HOLD",
            "production_recommendations":"DISABLED","publication_allowed":False,
            "authenticated_samples":0,"independent_oos_proven":False,
            "model_promotion_allowed":False,"external_witness_verified":False}

def permitted(authorized):
    return authorized is True and os.environ.get("GITHUB_ACTIONS","").lower()!="true"

def roster(values,limit,*,required=False):
    if type(values) is not list or len(values)>limit or (required and not values):
        raise ValueError("invalid digest roster")
    for v in values:fingerprint(v)
    if len(set(values))!=len(values):raise ValueError("duplicate digest")
    return sorted(values)

def read_member(fd,digest,limit):
    fingerprint(digest)
    flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
    with os.fdopen(os.open(digest+".json",flags,dir_fd=fd),"rb") as f:
        info=os.fstat(f.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1
                or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600
                or not 0<info.st_size<=limit):
            raise ValueError("unsafe private member")
        raw=f.read(limit+1)
        if len(raw)!=info.st_size or len(raw)>limit or sha(raw)!=digest:
            raise ValueError("private member digest or length mismatch")
        return raw

def review(*,repository,store,result_store,run_shas,primary_shas,secondary_shas,
           as_of,authorized=False):
    out=safety()
    if not permitted(authorized):
        return {**out,"review_passed":False,"reason":"PRIVATE_RUNTIME_REQUIRED"}
    try:
        now=stamp(as_of).isoformat()
        runs=roster(run_shas,MAX_RUNS,required=True)
        primary=roster(primary_shas,PRIMARY_MAX)
        secondary=roster(secondary_shas,SECONDARY_MAX)
        if set(primary)&set(secondary):
            raise ValueError("same bytes declared as two publishers")
        if Path(store).resolve()==Path(result_store).resolve():
            raise ValueError("separate result store required")
        fd=root_fd(store,repository)
        try:
            bodies=[];total=0
            for d in runs:
                b=read_member(fd,d,min(MAX_RUN_BYTES,MAX_COHORT_BYTES-total))
                total+=len(b);bodies.append(b)
        finally:os.close(fd)
        fd=root_fd(result_store,repository)
        try:
            result_total=0;streams=[]
            for ids in (primary,secondary):
                stream=[]
                for d in ids:
                    b=read_member(fd,d,min(MAX_BYTES,MAX_RESULT_BYTES-result_total))
                    result_total+=len(b);stream.append((d+".json",b))
                streams.append(stream)
        finally:os.close(fd)
        report=evaluate(bodies,*streams,as_of=now)
        if (report.get("submitted_runs")!=len(runs)
                or report.get("status")!="HOLD"
                or report.get("production_recommendations")!="DISABLED"
                or report.get("authenticated_samples")!=0
                or any(report.get(k) is not False for k in (
                    "independent_oos_proven","publication_allowed","model_promotion_allowed",
                    "external_forecast_witness_verified","training_admission"))):
            raise ValueError("unsafe evaluation report")
        # Private aggregate only: no raw bytes, paths, fixture IDs or credentials.
        return {**out,"review_passed":True,"run_count":len(runs),
                "primary_snapshot_count":len(primary),"secondary_snapshot_count":len(secondary),
                "run_bytes":total,"result_bytes":result_total,
                "selected_roster_locally_verified":True,"evaluation":report}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return {**out,"review_passed":False,"reason":"PRIVATE_REVIEW_REJECTED"}

def collect(*,repository,store,league,authorized=False):
    out=safety()
    if not permitted(authorized):
        return {**out,"collection_saved":False,"reason":"PRIVATE_RUNTIME_REQUIRED"}
    try:
        if store is None:raise ValueError("persistent private store required")
        fd=root_fd(store,repository)
        os.close(fd)
        key=os.environ.get("PROPLINE_API_KEY","")
        if not key:
            return {**out,"collection_saved":False,"reason":"NOT_CONFIGURED"}
        r=pilot(Path(repository),league,key=key,private_store=store)
        saved=r.get("private_run_saved") is True
        result={**out,"collection_saved":saved,
                "local_receipts":r["local_receipts"],"acquisition":r["acquisition"]}
        if saved:
            fingerprint(r["private_run_sha256"])
            result["private_run_sha256"]=r["private_run_sha256"]
        return result
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return {**out,"collection_saved":False,"reason":"PRIVATE_COLLECTION_REJECTED"}

def main():
    p=argparse.ArgumentParser(description="Authorized private research lifecycle; never publish")
    p.add_argument("--authorized-private-runtime",action="store_true")
    p.add_argument("--repository",type=Path,default=Path("."))
    sub=p.add_subparsers(dest="command",required=True)
    c=sub.add_parser("collect");c.add_argument("--store",type=Path,required=True)
    c.add_argument("--league",choices=tuple(SPORTS),required=True)
    r=sub.add_parser("review");r.add_argument("--store",type=Path,required=True)
    r.add_argument("--result-store",type=Path,required=True)
    r.add_argument("--run-sha",action="append",required=True)
    r.add_argument("--primary-sha",action="append",default=[])
    r.add_argument("--secondary-sha",action="append",default=[])
    a=p.parse_args()
    common=dict(repository=a.repository,store=a.store,authorized=a.authorized_private_runtime)
    if a.command=="collect":
        report=collect(**common,league=a.league);ok=report["collection_saved"]
    else:
        report=review(**common,result_store=a.result_store,run_shas=a.run_sha,
                      primary_shas=a.primary_sha,secondary_shas=a.secondary_sha,
                      as_of=datetime.now(timezone.utc).isoformat());ok=report["review_passed"]
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0 if ok else 2

if __name__=="__main__":raise SystemExit(main())
