"""Fail-closed integrity audit for research OOS evidence batches.

No automatic production promotion. A source must not attest conflicting
scores, and the batch must be ordered and have unique fixture identifiers.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from typing import Sequence
from ops.research_evidence_ledger_v1 import verify_record
from ops.research_result_settlement_v1 import ResultEvidence
from ops.research_evidence_oos_bridge_v1 import evidence_oos_report

def audit_evidence_batch(fixtures: Sequence[tuple[dict,dict,Sequence[ResultEvidence]]],
                         *, minimum_samples: int=300, block_size: int=20) -> dict:
    seen=set()
    previous=None
    publisher_conflicts=[]
    for baseline,challenger,results in fixtures:
        event=baseline.get("event_id")
        if not event or event in seen:
            raise ValueError("duplicate or missing fixture ID")
        if not verify_record(baseline) or not verify_record(challenger):
            raise ValueError("invalid forecast digest")
        seen.add(event)
        kickoff=datetime.fromisoformat(baseline["kickoff_at"])
        if kickoff.tzinfo is None or kickoff.utcoffset() is None:
            raise ValueError("timezone-aware kickoff required")
        if previous is not None and kickoff<=previous:
            raise ValueError("non-chronological fixture batch")
        previous=kickoff
        attestations={}
        for r in results:
            if r.event_id!=event or not r.publisher.strip():
                raise ValueError("result provenance mismatch")
            if not r.is_final:
                continue
            key=r.publisher.strip().casefold()
            score=(r.home_goals,r.away_goals)
            if key in attestations and attestations[key]!=score:
                publisher_conflicts.append({"event_id":event,"publisher":key})
            attestations[key]=score
    if publisher_conflicts:
        return {"status":"HOLD","reason":"CONFLICTING_PUBLISHER_ATTESTATIONS",
                "publisher_conflicts":publisher_conflicts,
                "sample_count":0,"production_recommendations":"DISABLED",
                "qualified_for_production":False}
    report=evidence_oos_report(fixtures,minimum_samples=minimum_samples,
                               block_size=block_size)
    # Manifest fingerprints record identity and results; this is not independent
    # timestamping or proof of a real historical data source.
    manifest=[{"event_id":b["event_id"],"baseline_sha256":b["sha256"],
               "challenger_sha256":c["sha256"],
               "results":sorted((r.publisher,r.home_goals,r.away_goals,
                                 r.is_final,r.observed_at.isoformat()) for r in rs)}
              for b,c,rs in fixtures]
    blob=json.dumps(manifest,sort_keys=True,separators=(",",":"),allow_nan=False)
    report["batch_sha256"]=hashlib.sha256(blob.encode()).hexdigest()
    report["evidence_count"]=len(manifest)
    report["status"]="HOLD"
    report["production_recommendations"]="DISABLED"
    report["qualified_for_production"]=False
    return report
