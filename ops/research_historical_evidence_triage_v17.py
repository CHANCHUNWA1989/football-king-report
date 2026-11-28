"""Unified read-only evidence triage for the original prematch ledger.
All archive observations remain candidate evidence, never authenticated samples.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from .research_live_intake_v4 import decode, MAX_BYTES
from .research_candidate_gap_v6 import stamp
from .research_archive_score_recovery_v14 import targets, compare, archive_snapshots, MAX_FILES as PRIMARY_MAX
from .research_two_publisher_recovery_v15 import crosscheck, secondary_snapshots, MAX_FILES as SECONDARY_MAX
from .research_missing_fixture_discovery_v16 import candidates, discover

def bounded(snapshots, limit, now, clock):
    """Use the same input bytes for all comparisons, reject future reports."""
    result=[]
    for label,body in snapshots:
        if len(result)>=limit:
            raise ValueError("archive count limit")
        try:
            if stamp(decode(body)[clock])>now:
                raise ValueError("future snapshot")
        except (KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError):
            body=b""
        result.append((label,body))
    return result

def review(raw, primary, secondary, *, as_of):
    now=stamp(as_of)
    all_rows=candidates(raw)
    fixed=targets(raw)
    first=bounded(primary,PRIMARY_MAX,now,"collected_utc")
    second=bounded(secondary,SECONDARY_MAX,now,"collected_utc")
    p=compare(raw,first)
    q=crosscheck(raw,first,second,as_of=now.isoformat())
    d=discover(raw,second,as_of=now.isoformat())
    pmap={x["key"]:x for x in p["cases"]}
    qmap={x["match_id"]:x for x in q["cases"]}
    dmap={x["key"]:x for x in d["cases"]}
    if len(pmap)!=len(fixed) or len(qmap)!=len(fixed) or set(pmap)&set(dmap):
        raise ValueError("inconsistent evidence partition")
    rows=[]
    for _,r in sorted(all_rows.items()):
        key=r["key"]
        a=pmap.get(key); b=qmap.get(a["match_id"]) if a else None
        c=dmap.get(key)
        if a and not b:raise ValueError("missing crosscheck case")
        state="IDENTITY_NOT_COVERED"; refs=[]
        if a:
            refs=[{"provider":"OpenLigaDB",**x} for x in a["observations"]]
            refs.extend({"provider":"thesportsdb",**x} for x in b["secondary_observations"])
            if "CONFLICT" in a["state"] or "CONFLICT" in b["state"]:
                state="CONFLICT_REVIEW"
            elif b["state"]=="TWO_PUBLISHER_EXACT_SCORE_CANDIDATE":
                state="TWO_PUBLISHER_SCORE_AGREEMENT"
            elif a["state"]=="SINGLE_PUBLISHER_OUTCOME_AGREEMENT":
                state="ONE_PUBLISHER_OUTCOME_AGREEMENT"
            else:state="FIXED_ID_RESULT_MISSING"
        elif c:
            refs=[{"provider":"thesportsdb",**x} for x in c["snapshot_references"]]
            state={"FIXTURE_AND_OUTCOME_CANDIDATE":"ONE_PUBLISHER_OUTCOME_AGREEMENT",
                   "FIXTURE_ID_CANDIDATE_ONLY":"IDENTITY_ONLY",
                   "NO_EXACT_FIXTURE_MATCH":"NO_EXACT_FIXTURE_MATCH",
                   "AMBIGUOUS_OR_CONFLICTING":"CONFLICT_REVIEW",
                   "RECORDED_OUTCOME_CONFLICT":"CONFLICT_REVIEW"}[c["state"]]
        blockers=["INDEPENDENT_FORECAST_WITNESS_MISSING","AUTHENTICATED_REGULATION_RESULT_MISSING",
                  "SOURCE_UPSTREAM_INDEPENDENCE_UNPROVEN"]
        if state=="CONFLICT_REVIEW":blockers.insert(0,"RESOLVE_IDENTITY_OR_SCORE_CONFLICT")
        elif state in ("NO_EXACT_FIXTURE_MATCH","IDENTITY_NOT_COVERED"):blockers.insert(0,"RECOVER_EXACT_FIXTURE_IDENTITY")
        elif state in ("IDENTITY_ONLY","FIXED_ID_RESULT_MISSING"):blockers.insert(0,"RECOVER_FINAL_SCORE")
        elif state=="ONE_PUBLISHER_OUTCOME_AGREEMENT":blockers.insert(0,"RECOVER_SECOND_PUBLISHER_SCORE")
        rows.append({"key":key,"league":r["league"],"state":state,"blockers":blockers,
                     "primary_candidate":a,"secondary_candidate":b,"discovery_candidate":c,
                     "references":refs,"authenticated":False})
    states=dict(Counter(x["state"] for x in rows))
    return {"schema":"unified-historical-evidence-triage-v17","status":"HOLD",
            "production_recommendations":"DISABLED","ledger_sha256":hashlib.sha256(raw).hexdigest(),
            "as_of":now.isoformat(),"ledger_rows":len(rows),"states":states,
            "outcome_corroborated_candidates":states.get("ONE_PUBLISHER_OUTCOME_AGREEMENT",0)+states.get("TWO_PUBLISHER_SCORE_AGREEMENT",0),
            "primary_snapshots_examined":len(first),"secondary_snapshots_examined":len(second),
            "invalid_primary_snapshots":p["invalid_snapshots"],"invalid_secondary_snapshots":d["invalid_snapshots"],
            "blocker_counts":dict(Counter(b for x in rows for b in x["blockers"])),
            "authenticated_samples":0,"model_promotion_allowed":False,
            "original_ledger_mutated":False,"cases":rows}

def from_root(root, *, as_of):
    with (root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    return review(raw,archive_snapshots(root/"sources/live_germany/history",targets(raw)),
                  secondary_snapshots(root/"sources/history",candidates(raw)),as_of=as_of)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    a=p.parse_args()
    report=from_root(a.root,as_of=datetime.now(timezone.utc).isoformat())
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
