"""Fail-closed research promotion triage; never grants production authorization."""
from collections.abc import Mapping
from math import isfinite
from ops.live_snapshot_market_audit_20261126 import aware

METRICS=("log_loss","brier","rps","exact_score","tail_brier")
MIN_FIXTURES=500
MIN_WEEKS=30
MIN_IMPROVEMENT=.005

def _number(v):
    return type(v) in (int,float) and isfinite(v)

def _digest(v):
    return isinstance(v,str) and len(v)==64 and all(x in "0123456789abcdef" for x in v)

def triage(report, used_cohorts):
    """Assess claimed evidence only. A digest is not source authentication.
    Explicitly require actual production comparator and guardrails.
    """
    reasons=set()
    if not isinstance(report,Mapping) or not isinstance(used_cohorts,(list,tuple,set)):
        return _result({"INVALID_INPUT"})
    if any(not _digest(v) for v in used_cohorts):
        reasons.add("INVALID_COHORT_REGISTRY")
    cohort=report.get("cohort_sha256")
    if not _digest(cohort): reasons.add("INVALID_COHORT")
    elif cohort in used_cohorts: reasons.add("REUSED_COHORT")
    if report.get("retrospective_only") is not False: reasons.add("RETROSPECTIVE_OR_UNKNOWN")
    if report.get("comparator_role")!="CURRENT_PRODUCTION": reasons.add("PRODUCTION_COMPARATOR_MISSING")
    a,b=report.get("baseline_id"),report.get("challenger_id")
    if not all(isinstance(v,str) and v.strip() for v in (a,b)) or a==b:
        reasons.add("INVALID_MODEL_IDENTITIES")
    for key in ("manifest_sha256","forecast_archive_sha256","settlement_archive_sha256"):
        if not _digest(report.get(key)): reasons.add("INVALID_"+key.upper())
    try:
        if not aware(report.get("frozen_at"))<aware(report.get("first_decision_at"))<=aware(report.get("last_decision_at"))<aware(report.get("evaluated_at")):
            reasons.add("CHRONOLOGY_INVALID")
    except (ValueError,TypeError,OverflowError):
        reasons.add("CHRONOLOGY_INVALID")
    for key,minimum in (("n",MIN_FIXTURES),("weeks",MIN_WEEKS)):
        v=report.get(key)
        if type(v) is not int or v<minimum: reasons.add("INSUFFICIENT_"+key.upper())
    if report.get("complete_paired_cohort") is not True: reasons.add("INCOMPLETE_PAIRED_COHORT")
    if report.get("preregistered_primary")!="log_loss": reasons.add("PRIMARY_NOT_PREREGISTERED")
    if report.get("multiplicity_controlled") is not True: reasons.add("MULTIPLICITY_UNVERIFIED")
    if report.get("independent_reproduction") is not True: reasons.add("REPRODUCTION_UNVERIFIED")
    deltas=report.get("deltas")
    intervals=report.get("intervals")
    if not isinstance(deltas,Mapping) or not isinstance(intervals,Mapping):
        reasons.add("METRIC_EVIDENCE_MISSING")
    else:
        for m in METRICS:
            d=deltas.get(m);ci=intervals.get(m)
            if not _number(d) or not isinstance(ci,(list,tuple)) or len(ci)!=2 or not all(_number(v) for v in ci) or not ci[0]<=d<=ci[1]:
                reasons.add("INVALID_METRIC_"+m.upper());continue
            # Provisional conservative guardrail; not a validated power threshold.
            if m=="log_loss":
                if d> -MIN_IMPROVEMENT or ci[1]>=0: reasons.add("PRIMARY_IMPROVEMENT_UNPROVEN")
            elif d>0 or ci[1]>0: reasons.add("GUARDRAIL_"+m.upper())
    return _result(reasons)

def _result(reasons):
    return {"status":"HOLD" if reasons else "REVIEW_REQUIRED",
            "reasons":sorted(reasons),"thresholds_provisional":True,
            "attestation_verified":False,"promotion_authorized":False,
            "deployment":"HOLD","recommendations":"DISABLED","positive_ev_verified":False}
