"""Reconstruct a private V48 run from caller-supplied original historical inputs.
Completeness is relative to these supplied bytes, not to the provider universe.
No network, publication, external witness, or promotion.
"""
import json
from .research_private_run_store_v48 import verify_run,encode_run,unb64
from .research_integrated_fusion_v45 import prepare
from .research_live_intake_v4 import MAX_BYTES
from .research_archive_score_recovery_v14 import MAX_FILES as PRIMARY_MAX
from .research_two_publisher_recovery_v15 import MAX_FILES as SECONDARY_MAX

MAX_ARCHIVE_BYTES=128*1024*1024

def recheck(run_raw,ledger_raw,primary,secondary,*,include_supplemental):
    if type(include_supplemental) is not bool:
        raise ValueError("explicit history mode required")
    if not isinstance(ledger_raw,bytes) or not 0<len(ledger_raw)<=MAX_BYTES:
        raise ValueError("ledger size")
    size=0
    for stream,limit in ((primary,PRIMARY_MAX),(secondary,SECONDARY_MAX)):
        if not isinstance(stream,list) or len(stream)>limit:
            raise ValueError("archive roster")
        for row in stream:
            if not isinstance(row,tuple) or len(row)!=2:
                raise ValueError("archive entry")
            label,body=row
            if not isinstance(label,str) or not label or not isinstance(body,bytes) or not 0<len(body)<=MAX_BYTES:
                raise ValueError("archive bytes")
            size+=len(body)
            if size>MAX_ARCHIVE_BYTES:
                raise ValueError("archive byte budget")
    audit=verify_run(run_raw)
    d=json.loads(run_raw)
    batch={**d["batch"],"raw":unb64(d["batch"]["raw"])}
    packets,report=prepare(ledger_raw,primary,secondary,None,[batch],
                           as_of=d["forecast_utc"],include_supplemental=include_supplemental)
    if not packets or encode_run(batch,packets)!=run_raw:
        raise ValueError("full original input replay mismatch")
    return {**audit,"schema":"private-full-replay-v1",
            "historical_reference_bytes_rechecked":True,
            "supplied_input_roster_reproduced":True,
            "history_candidates":report["history_inventory"]["history_candidates"],
            "history_mode":"expanded" if include_supplemental else "ledger_only",
            "cohort_completeness_proven":False,"training_admission":False,
            "model_promotion_allowed":False}
