"""Read-only offline qualification rehearsal on a pinned existing ledger.

Real archived observations, synthetic missing-source envelopes. Never imply
daily live collection, authenticated results or market execution.
"""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime,timezone
from evidence_merge import validate
from forward_daily_scorecard import publish as daily_publish
from fourway_calibration_diagnostic import build as calibration
from production_gate import gate
from ops.operations_review import publish as ops_publish
from research_strict_json import unique_object,reject_constant
from settled_calibration_replay import PIN,MAX_BYTES

def verify(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_BYTES:
        raise ValueError("LEDGER_SIZE")
    if hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()!=PIN:
        raise ValueError("LEDGER_PIN_CHANGED")
    doc=json.loads(raw.decode(),object_pairs_hook=unique_object,parse_constant=reject_constant)
    validate(doc)
    return doc

def rehearsal(raw):
    doc=verify(raw)
    n=doc["n"]
    stamp=datetime.fromisoformat(doc["checked_utc"].replace("Z","+00:00"))
    diag=calibration(doc["samples"],checked_utc=doc["checked_utc"])
    center={"production_recommendations":"DISABLED","generated_utc":stamp.isoformat(),
            "fourway_calibration_diagnostic":diag}
    validation={"production_recommendations":"DISABLED","status":"HOLD","measurements":None}
    qualified=gate(center,doc,validation)
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        ledger=root/"sealed.json"
        ledger.write_bytes(raw)
        (root/"index.html").write_text("<html><body></body></html>",encoding="utf-8")
        daily=daily_publish(ledger,root)
        for name,payload in (("production_gate",qualified),("research_center",center)):
            (root/(name+".json")).write_text(json.dumps(payload,allow_nan=False),encoding="utf-8")
        monitor=ops_publish(root,now=stamp)
        # Re-read actual serialized artifacts; no mock publisher functions.
        monitor=json.loads((root/"operations_review.json").read_text())
        daily=json.loads((root/"forward_daily_scorecard.json").read_text())
        if ledger.read_bytes()!=raw:
            raise ValueError("LEDGER_MUTATED")
        if not (daily["settled_observations"]==qualified["settled_samples"]==monitor["counts"]["recorded_settled_research"]==n):
            raise ValueError("SETTLED_COUNT_MISMATCH")
        if monitor["counts"]["fourway_descriptive_cases"]!=diag["cohort_count"] or diag["cohort_count"]+diag["excluded_count"]!=n:
            raise ValueError("COHORT_COUNT_MISMATCH")
        if any(d["production_recommendations"]!="DISABLED" for d in (daily,qualified,monitor,diag)):
            raise ValueError("UNSAFE_OUTPUT")
        if qualified["authenticated_forward_samples"] or monitor["authenticated_forward_samples"] or daily["independently_verified_observations"]:
            raise ValueError("FALSE_AUTHENTICATION")
        if monitor["counts"]["time_valid_market_pairs"] is not None or monitor["counts"]["public_window_observations"] is not None:
            raise ValueError("MISSING_DATA_INVENTED")
        if not all((root/p).is_file() for p in ("daily-review.html","operations-review.html")):
            raise ValueError("MOBILE_OUTPUT_MISSING")
        return {"source_blob":PIN,"archived_checked_utc":doc["checked_utc"],
                "recorded_research_samples":n,"fourway_cases":diag["cohort_count"],
                "excluded_fourway_cases":diag["excluded_count"],
                "recorded_research_weeks":qualified["recorded_research_week_blocks"],
                "recorded_leagues_with_40":qualified["recorded_research_leagues_with_40"],
                "research_league_counts":qualified["validation_progress"]["per_league_settled"],
                "authenticated_forward_samples":0,"remaining_authenticated_samples":qualified["remaining_authenticated_samples"],
                "remaining_authenticated_weeks":qualified["remaining_authenticated_weeks"],
                "remaining_authenticated_leagues":qualified["remaining_authenticated_leagues"],
                "failed_conditions":qualified["failed_conditions"],
                "daily_error_summary":daily["error_review"]["summary"],
                "mobile_outputs_verified":True,"ledger_unchanged":True,
                "missing_source_alerts":sum(a["code"].startswith("MISSING_") for a in monitor["alerts"]),
                "synthetic_source_envelopes":True,"actual_daily_run":False,
                "positive_ev_verified":False,"production_recommendations":"DISABLED","status":"HOLD"}

if __name__=="__main__":
    raw=subprocess.check_output(["git","cat-file","blob",PIN],timeout=10)
    print(json.dumps(rehearsal(raw),sort_keys=True,allow_nan=False))
