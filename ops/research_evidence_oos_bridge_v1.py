"""Research-only evidence-to-OOS bridge, without manual outcome entry.

Both forecasts must have valid pre-match digests for the same fixture.
A result must be agreed by two independent final-score publishers.
No production activation and no inference of genuine holdout independence.
"""
from __future__ import annotations
from datetime import datetime
from typing import Sequence
from ops.research_evidence_ledger_v1 import verify_record
from ops.research_result_settlement_v1 import ResultEvidence,audit_settlement
from ops.research_paired_oos_v1 import PairedPrediction,paired_oos_report

def build_paired_evidence(baseline: dict, challenger: dict,
                          results: Sequence[ResultEvidence]) -> PairedPrediction:
    if not verify_record(baseline) or not verify_record(challenger):
        raise ValueError("forecast integrity check failed")
    if baseline.get("status")!="HOLD" or challenger.get("status")!="HOLD":
        raise ValueError("only frozen research forecasts accepted")
    for key in ("event_id","kickoff_at"):
        if baseline.get(key)!=challenger.get(key):
            raise ValueError("baseline and challenger must match fixture")
    kickoff=datetime.fromisoformat(baseline["kickoff_at"])
    for forecast in (baseline,challenger):
        prediction_at=datetime.fromisoformat(forecast["forecast_at"])
        if prediction_at>=kickoff:
            raise ValueError("post-kickoff prediction rejected")
    settled=audit_settlement(baseline,results)
    if settled["status"]!="SETTLED_RESEARCH":
        raise ValueError("two-source final result not established")
    h,a=settled["final_score"]
    outcome="home" if h>a else ("away" if h<a else "draw")
    return PairedPrediction(
        event_id=baseline["event_id"],kickoff=kickoff,outcome=outcome,
        baseline=dict(baseline["one_x_two"]),
        challenger=dict(challenger["one_x_two"]),
        independently_verified=True)

def evidence_oos_report(fixtures: Sequence[tuple[dict,dict,Sequence[ResultEvidence]]],
                        *,minimum_samples: int=300,block_size: int=20) -> dict:
    paired=[build_paired_evidence(b,c,r) for b,c,r in fixtures]
    report=paired_oos_report(paired,minimum_samples=minimum_samples,
                             block_size=block_size)
    report["evidence_linked"]=True
    report["independent_holdout_proven"]=False
    report["production_recommendations"]="DISABLED"
    report["qualified_for_production"]=False
    return report
