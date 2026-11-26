"""Join freshly reverified witness cases to frozen schedule candidates; no credit."""
import argparse
import json
from pathlib import Path
from collections import Counter
from datetime import timedelta
import dixon_coles_witness_audit as witness
from forward_fixture_candidate_replay import BLOBS, read, audit, key, stamp
from source_fixture_identity import metadata_from_event_id

def join(candidates,cases):
    result=[]
    for c in candidates:
        k=key({**c,"kickoff_utc":c["kickoff_utc_recorded"]})
        expected=str(c["openligadb_match_id"])
        rows=[r for r in cases if key({**r,"kickoff_utc":r["kickoff_utc_recorded"]})==k]
        native=[r for r in cases if metadata_from_event_id(r["event_id"]).get("source_fixture_identity",{}).get("match_id")==expected]
        state="NO_WITNESSED_FORECAST_MATCH"
        if len(rows)>1 or len(native)>1:
            state="AMBIGUOUS_FORECAST"
        elif native and (not rows or native[0]!=rows[0]):
            state="NATIVE_ID_FIXTURE_CONFLICT"
        elif rows:
            r=rows[0]
            typed=metadata_from_event_id(r["event_id"]).get("source_fixture_identity")
            if typed is not None and typed["match_id"]!=expected:
                state="NATIVE_ID_FIXTURE_CONFLICT"
            elif r["observed_before_recorded_kickoff"] is not True or not stamp(r["source_prediction_utc"])<=stamp(r["candidate_generated_utc"])<=stamp(r["verified_tlog_utc"])<k[3]-timedelta(minutes=10):
                state="WITNESS_CLOCK_REJECTED"
            elif native:
                state="EXACT_NATIVE_ID_WITNESS_CANDIDATE"
            else:
                state="TEAM_TIME_WITNESS_ONLY"
        result.append({"openligadb_match_id":c["openligadb_match_id"],"thesportsdb_event_id":c["thesportsdb_event_id"],
          "state":state,"source_identity_authenticated":False,"actual_kickoff_authenticated":False,"result_authenticated":False,"verified_forward_sample_credit":0})
    return {"schema":"forward-candidate-witness-overlap-v1","frozen_candidates":len(candidates),"witness_cases":len(cases),
      "counts":dict(Counter(r["state"] for r in result)),"rows":result,"verified_forward_sample_credit":0,"status":"HOLD","production_recommendations":"DISABLED"}

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--proof",required=True);a=p.parse_args()
    frozen=audit(*(read(a.root,path) for path in BLOBS))
    report=witness.audit(Path(a.proof),source_sha="e5fd3e487a0eb18c955fe5a2d0c384fcf2222d08",workflow_sha="e5fd3e487a0eb18c955fe5a2d0c384fcf2222d08",run_id="45594300848",attempt="1")
    if not all(report.get(k) is True for k in ("audit_completed","signature_identity_and_subjects_verified","candidate_bytes_formula_source_binding_verified")) or report["total_candidates"]!=27 or len(report["cases"])!=27:raise ValueError("WITNESS_NOT_VERIFIED")
    out=join(frozen["candidates"],report["cases"]);out["verified_tlog_utc"]=report["verified_tlog_utc"];out["subject_sha256"]=report["subject_sha256"]
    print(json.dumps(out,allow_nan=False,sort_keys=True))
if __name__=="__main__":main()
