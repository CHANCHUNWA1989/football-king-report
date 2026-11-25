"""One-shot offline batch audit for authorized upstream collectors.
No provider calls, recommendations, betting, or persistent scheduler.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import time
from vnext_live_evidence_cut import audit_cut

MAX_BYTES = 2_000_000
MAX_FIXTURES = 100
# Only fixed internal reason codes may appear in aggregate diagnostics.
CUT_REASONS = frozenset({
    "INVALID_CUT", "CUT_COMMITMENT_MISMATCH", "MODEL_CUT_REJECTED",
    "QUOTE_CUT_REJECTED", "CROSS_CUT_STATE_MISMATCH", "SCORE_RECORD_NOT_BOUND",
    "EVENT_TIME_CONFLICT", "UNSUPPORTED_QUOTE_SCOPE",
})

def report(reason, total=0, accepted=0, rejected=None, cut_reasons=None):
    return {"schema":"football-king-live-auto-audit-v1", "status":"HOLD",
            "reason":reason, "production_recommendations":"DISABLED",
            "fixture_count":total, "structurally_consistent":accepted,
            "rejection_counts":rejected or {},
            "evidence_cut_reason_counts":cut_reasons or {}, "source_authenticated":False,
            "actual_xg_verified":False, "positive_ev_verified":False,
            "model_edge":None, "betting_recommendation_allowed":False}

def audit_batch(payload, now):
    if type(now) is not int or type(payload) is not dict or set(payload)!={"cases"}:
        return report("INVALID_BATCH")
    cases=payload["cases"]
    if type(cases) is not list or len(cases)>MAX_FIXTURES:
        return report("INVALID_BATCH")
    if not cases:
        return report("NO_INPUT")
    # Reject every member of a duplicate fixture group, never choose a winner.
    def identity(row):
        try:
            fid=row["envelope"]["a"]["fixture_id"]
            return fid if type(fid) is str and 0<len(fid)<=128 else None
        except (KeyError, TypeError):
            return None
    counts=Counter(identity(row) for row in cases)
    accepted=0
    rejected=Counter()
    cut_reasons=Counter()
    for row in cases:
        fid=identity(row)
        if type(row) is not dict or set(row)!={"envelope","snapshot","expected_digest"} or fid is None:
            rejected["INVALID_CASE"]+=1
            continue
        if counts[fid]>1:
            rejected["DUPLICATE_FIXTURE"]+=1
            continue
        result=audit_cut(row["envelope"],row["snapshot"],row["expected_digest"],now)
        if result.get("cut_status")=="STRUCTURAL_RESEARCH_ONLY":
            accepted+=1
        else:
            # Do not echo source content or exceptions.
            rejected["EVIDENCE_CUT_REJECTED"]+=1
            reason=result.get("reason")
            if type(reason) is not str or reason not in CUT_REASONS:
                reason="OTHER_CUT_REJECTION"
            cut_reasons[reason]+=1
    return report("UNAUTHENTICATED_BATCH" if accepted else "NO_CONSISTENT_INPUT",
                  len(cases),accepted,dict(sorted(rejected.items())),
                  dict(sorted(cut_reasons.items())))

def _unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[k]=v
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description="Read-only batch evidence audit")
    p.add_argument("input",type=Path)
    args=p.parse_args(argv)
    try:
        with args.input.open("rb") as f:
            raw=f.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise ValueError("INPUT_TOO_LARGE")
        payload=json.loads(raw.decode("utf-8"),object_pairs_hook=_unique)
        result=audit_batch(payload,int(time.time()))
    except (OSError,ValueError,TypeError,RecursionError):
        result=report("INPUT_UNAVAILABLE_OR_INVALID")
    print(json.dumps(result,sort_keys=True,allow_nan=False))
    # No structurally acceptable case is distinguishable from a healthy cycle.
    return 0 if result["structurally_consistent"] else 2

if __name__=="__main__":
    raise SystemExit(main())
