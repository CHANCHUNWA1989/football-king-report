"""Private paired evaluation gated on complete reconstruction of each supplied run.

All supplied pre-match inputs must reproduce their saved run before any score
evaluation. This does not authenticate external clocks, source independence,
or the completeness of the submitted set of runs. No network or file writes.
"""
from .research_private_full_replay import recheck,MAX_ARCHIVE_BYTES
from .research_private_evaluation_v50 import evaluate,MAX_RUNS,MAX_COHORT_BYTES
from .research_private_run_store_v48 import MAX_RUN_BYTES
from .research_prospective_fusion_v38 import exact,sha
from .research_live_intake_v4 import MAX_BYTES
from .research_archive_score_recovery_v14 import MAX_FILES as PRIMARY_MAX
from .research_two_publisher_recovery_v15 import MAX_FILES as SECONDARY_MAX

def evaluate_replayed(bundles,primary,secondary,*,as_of):
    if not isinstance(bundles,list) or len(bundles)>MAX_RUNS:
        raise ValueError("run roster")
    total_runs=0;total_evidence=0;seen=set();runs=[]
    def account(stream,limit):
        nonlocal total_evidence
        if not isinstance(stream,list) or len(stream)>limit:
            raise ValueError("archive roster")
        for row in stream:
            if not isinstance(row,tuple) or len(row)!=2:
                raise ValueError("archive entry")
            label,body=row
            if not isinstance(label,str) or not label or not isinstance(body,bytes) or not 0<len(body)<=MAX_BYTES:
                raise ValueError("archive bytes")
            total_evidence+=len(body)
            if total_evidence>MAX_ARCHIVE_BYTES:raise ValueError("cohort evidence budget")
    account(primary,PRIMARY_MAX);account(secondary,SECONDARY_MAX)
    for b in bundles:
        exact(b,"run_raw ledger_raw primary secondary include_supplemental")
        raw=b["run_raw"];ledger=b["ledger_raw"]
        if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_RUN_BYTES:
            raise ValueError("run size")
        if not isinstance(ledger,bytes) or not 0<len(ledger)<=MAX_BYTES:
            raise ValueError("ledger size")
        total_runs+=len(raw);total_evidence+=len(ledger)
        if total_runs>MAX_COHORT_BYTES or total_evidence>MAX_ARCHIVE_BYTES:
            raise ValueError("cohort byte budget")
        digest=sha(raw)
        if digest in seen:raise ValueError("duplicate run")
        seen.add(digest);runs.append(raw)
        account(b["primary"],PRIMARY_MAX);account(b["secondary"],SECONDARY_MAX)
    receipts=0
    for b in bundles:
        r=recheck(b["run_raw"],b["ledger_raw"],b["primary"],b["secondary"],
                  include_supplemental=b["include_supplemental"])
        if r["run_sha256"]!=sha(b["run_raw"]) or r["supplied_input_roster_reproduced"] is not True:
            raise ValueError("replay mismatch")
        receipts+=r["local_receipts"]
    result=evaluate(runs,primary,secondary,as_of=as_of)
    if result["submitted_fixtures"]!=receipts:
        raise ValueError("evaluation roster mismatch")
    return {**result,"schema":"private-replayed-paired-evaluation-v1",
            "original_input_replay_required":True,"replayed_runs":len(runs),
            "replayed_receipts":receipts,
            "supplied_input_rosters_reproduced":bool(runs),
            "historical_reference_bytes_rechecked":bool(runs),
            "cohort_completeness_proven":False}
