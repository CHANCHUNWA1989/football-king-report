"""Pinned archive error attribution and provenance inventory, never admission.

Outcome-conditioned diagnostics are retrospective, not prediction features.
No identities or prices are published; no fitting or automatic selection.
"""
import json
import math
import subprocess
from collections import Counter,defaultdict
from datetime import timedelta
from evidence_merge import aware,validate
from qualification_rehearsal import verify
from settled_calibration_replay import PIN
from model_market_bias_audit import audit
from fourway_calibration_diagnostic import score

CLASSES=("HOME","DRAW","AWAY")
def normalize(p):
    return [x/math.fsum(p) for x in p]

def top(p):
    # Match the existing scorecard's deterministic first-index tie rule.
    return max(range(3),key=lambda i:p[i])

def summary(rows):
    n=len(rows)
    if not n:return {"n":0,"model_log_loss":None,"market_log_loss":None,"model_minus_market_log_loss_sum":0.0,"model_brier":None,"market_brier":None}
    pairs=[(score(normalize(r["p"]),r["y"]),score(normalize(r["m"]),r["y"])) for r in rows]
    a=math.fsum(x[0][0] for x in pairs);b=math.fsum(x[1][0] for x in pairs)
    return {"n":n,"model_log_loss":a/n,"market_log_loss":b/n,
            "model_minus_market_log_loss_sum":math.fsum(x[0][0]-x[1][0] for x in pairs),
            "model_brier":math.fsum(x[0][1] for x in pairs)/n,
            "market_brier":math.fsum(x[1][1] for x in pairs)/n,
            "model_top_hits":sum(top(r["p"])==r["y"] for r in rows),
            "market_top_hits":sum(top(r["m"])==r["y"] for r in rows)}

def identity_metadata(r):
    event=r.get("forecast_event_id")
    s=r.get("source_fixture_identity")
    return (isinstance(event,str) and bool(event.strip()),
            isinstance(s,dict) and isinstance(s.get("provider"),str) and bool(s["provider"].strip())
            and isinstance(s.get("match_id"),str) and bool(s["match_id"].strip()))

def inventory(rows):
    counts=Counter()
    missing=Counter()
    for r in rows:
        f,s=identity_metadata(r)
        counts["forecast_event_id_present"]+=int(f)
        counts["source_identity_present"]+=int(s)
        counts["both_identity_fields_present"]+=int(f and s)
        counts["explicit_unauthenticated_source_identity"]+=int(r.get("source_fixture_identity_status")=="UNAUTHENTICATED")
        counts["explicit_ineligible_for_model_scoring"]+=int(r.get("eligible_for_model_scoring") is False)
        counts["explicit_independently_unverified"]+=int(r.get("independently_verified") is False)
        # This is a presence check only; there is no trust anchor or external recheck.
        if not f:missing["FORECAST_EVENT_ID_MISSING"]+=1
        if not s:missing["SOURCE_FIXTURE_IDENTITY_MISSING"]+=1
        missing["INDEPENDENT_RESULT_PROOF_NOT_ADMITTED"]+=1
        missing["EXTERNAL_FORECAST_ATTESTATION_NOT_ADMITTED"]+=1
        missing["EXECUTABLE_MARKET_QUOTE_NOT_ADMITTED"]+=1
    return {"metadata_counts":dict(counts),"overlapping_missing_requirements":dict(missing),
            "authenticated_admission_implemented":False,"authenticated_forward_samples":0}

def build(doc):
    rows=validate(doc)
    audit(rows,archived_at_utc=doc["checked_utc"])
    checked=aware(doc["checked_utc"])
    if any(aware(r["kickoff_utc"])+timedelta(minutes=120)>checked for r in rows):
        raise ValueError("IMMATURE_SETTLEMENT")
    outcomes={label:summary([r for r in rows if r["y"]==i]) for i,label in enumerate(CLASSES)}
    disagreements={"same_top":[],"different_top":[]}
    age={"0_to_1h":[],"over_1_to_6h":[],"over_6h":[]}
    for r in rows:
        disagreements["same_top" if top(r["p"])==top(r["m"]) else "different_top"].append(r)
        delta=(aware(r["forecast_utc"])-aware(r["market_utc"])).total_seconds()/3600
        age["0_to_1h" if delta<=1 else "over_1_to_6h" if delta<=6 else "over_6h"].append(r)
    groups={"actual_outcome":outcomes,"top_choice_agreement":{k:summary(v) for k,v in disagreements.items()},
            "market_to_forecast_metadata_lag":{k:summary(v) for k,v in age.items()}}
    pooled=summary(rows)
    for cells in groups.values():
        if sum(c["n"] for c in cells.values())!=len(rows) or not math.isclose(math.fsum(c["model_minus_market_log_loss_sum"] for c in cells.values()),pooled["model_minus_market_log_loss_sum"],abs_tol=1e-10):
            raise ValueError("PARTITION_MISMATCH")
    return {"source_blob":PIN,"archived_checked_utc":doc["checked_utc"],
            "pooled":pooled,"partitions":groups,"provenance_inventory":inventory(rows),
            "outcome_conditioning_retrospective":True,"market_age_metadata_not_authenticated":True,
            "no_causal_attribution":True,"selected_model":None,"new_forward_credit":0,
            "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}

if __name__=="__main__":
    raw=subprocess.check_output(["git","cat-file","blob",PIN],timeout=10)
    print(json.dumps(build(verify(raw)),sort_keys=True,allow_nan=False))
