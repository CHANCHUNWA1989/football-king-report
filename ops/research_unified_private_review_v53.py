"""V53: one private audit entry for two distinct research cohorts.

Never pool or rank these heterogeneous samples. No network, deployment,
publication, external source authentication or new model fitting.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import os
from .research_private_runtime_v52 import permitted, read_member, review as private_review
from .research_private_run_store_v48 import root_fd
from .research_live_intake_v4 import decode
from .research_unified_market_benchmark_v44 import run as live_review
from .research_candidate_gap_v6 import stamp
from .research_prospective_fusion_v38 import fingerprint
from .research_unified_cohort_v43 import MAX_CASES
from .research_unified_prematch_replay_v35 import digest

MAX_REQUEST_BYTES=16*1024*1024
MAX_CAPTURE_BYTES=256*1024
MAX_CAPTURES=6

def safety():
    return {"schema":"unified-private-review-v53","status":"HOLD",
            "production_recommendations":"DISABLED","publication_allowed":False,
            "independent_oos_proven":False,"authenticated_samples":0,
            "model_promotion_allowed":False,"cohorts_pooled":False,
            "cross_cohort_ranking_allowed":False}

def raw_bytes(v):
    if type(v) is not str or not 0<len(v)<=2*MAX_CAPTURE_BYTES or len(v)%2:
        raise ValueError("invalid capture encoding")
    b=bytes.fromhex(v)
    if b.hex()!=v:
        raise ValueError("noncanonical capture encoding")
    return b

def load_live_request(raw):
    # The common strict decoder has a smaller per-envelope bound.
    # Apply it to the request as well; never bypass strict JSON parsing.
    doc=decode(raw)
    fields={"expected_ids","executions","finals","model_release",
            "train_start","train_cutoff","test_end"}
    if type(doc) is not dict or set(doc)!=fields:
        raise ValueError("unexpected live request schema")
    executions=doc["executions"]
    if type(executions) is not list or not 1<=len(executions)<=MAX_CASES:
        raise ValueError("invalid executions")
    n=0
    for ex in executions:
        if type(ex) is not dict or set(ex)!={"roster","records","cutoff",
                "live_cases","live_as_of","model_release"}:
            raise ValueError("unexpected execution fields")
        if type(ex["live_cases"]) is not dict:
            raise ValueError("invalid live cases")
        for case in ex["live_cases"].values():
            n+=1
            if n>MAX_CASES:raise ValueError("cohort size")
            args=case["inputs"]
            args["prematch_raw"]=raw_bytes(args["prematch_raw"])
            captures=args["live_raw_captures"]
            if type(captures) is not list or not 1<=len(captures)<=MAX_CAPTURES:
                raise ValueError("invalid capture roster")
            args["live_raw_captures"]=[raw_bytes(x) for x in captures]
    return doc

def run(*,repository,store,result_store,live_store,live_sha,run_shas,
        primary_shas,secondary_shas,as_of,authorized=False):
    out=safety()
    if not permitted(authorized):
        return {**out,"review_passed":False,"reason":"PRIVATE_RUNTIME_REQUIRED"}
    try:
        now=stamp(as_of).isoformat()
        if len({Path(x).resolve() for x in (store,result_store,live_store)})!=3:
            raise ValueError("three separate private stores required")
        fingerprint(live_sha)
        fd=root_fd(live_store,repository)
        try:raw=read_member(fd,live_sha,MAX_REQUEST_BYTES)
        finally:os.close(fd)
        args=load_live_request(raw)
        for execution in args["executions"]:
            execution["root"]=Path(repository)
        a=private_review(repository=repository,store=store,result_store=result_store,
                         run_shas=run_shas,primary_shas=primary_shas,
                         secondary_shas=secondary_shas,as_of=now,authorized=authorized)
        b=live_review(**args,as_of=now)
        if (a.get("review_passed") is not True or b.get("structural_review_passed") is not True
                or any(x.get("status")!="HOLD" or x.get("production_recommendations")!="DISABLED"
                       or x.get("independent_oos_proven") is not False
                       or x.get("model_promotion_allowed") is not False for x in (a,b))
                or a.get("authenticated_samples")!=0
                or a.get("publication_allowed") is not False
                or b.get("source_authenticity_verified") is not False
                or b.get("external_timestamp_verified") is not False
                or b.get("certified_ev") is not False):
            raise ValueError("child review rejected")
        result={**out,"review_passed":True,"as_of_utc":now,
                "private_prematch_evaluation":a["evaluation"],
                "live_linked_prematch_benchmark":b["benchmark"],
                "live_declared_count":b["declared_count"],
                "live_excluded_count":b["excluded_prematch_outside_test_window"],
                "live_market_comparison_performed":b["market_comparison_performed"],
                "live_request_sha256":live_sha,
                "live_review_sha256":b["local_review_sha256"],
                "private_run_roster_sha256":digest(sorted(run_shas)),
                "primary_roster_sha256":digest(sorted(primary_shas)),
                "secondary_roster_sha256":digest(sorted(secondary_shas))}
        result["local_review_sha256"]=digest(result)
        return result
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return {**out,"review_passed":False,"reason":"UNIFIED_PRIVATE_REVIEW_REJECTED"}

def main():
    p=argparse.ArgumentParser(description="Private two-cohort audit; never publish")
    p.add_argument("--authorized-private-runtime",action="store_true")
    p.add_argument("--repository",type=Path,default=Path("."))
    for k in ("store","result-store","live-store"):p.add_argument("--"+k,type=Path,required=True)
    p.add_argument("--live-sha",required=True)
    p.add_argument("--run-sha",action="append",required=True)
    p.add_argument("--primary-sha",action="append",default=[])
    p.add_argument("--secondary-sha",action="append",default=[])
    a=p.parse_args()
    r=run(repository=a.repository,store=a.store,result_store=a.result_store,
          live_store=a.live_store,live_sha=a.live_sha,run_shas=a.run_sha,
          primary_shas=a.primary_sha,secondary_shas=a.secondary_sha,
          as_of=datetime.now(timezone.utc).isoformat(),authorized=a.authorized_private_runtime)
    print(json.dumps(r,sort_keys=True,allow_nan=False))
    return 0 if r["review_passed"] else 2

if __name__=="__main__":raise SystemExit(main())
