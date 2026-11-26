"""Join freshly reverified witness cases to frozen schedule candidates; no credit."""
import argparse
import json
import hashlib
import math
from pathlib import Path
from collections import Counter
from datetime import timedelta
import dixon_coles_witness_audit as witness
from forward_fixture_candidate_replay import BLOBS, read, audit, key, stamp
from source_fixture_identity import metadata_from_event_id
from forward_fixture_postmatch_diagnostic import compare, read_later
from model_dixon_coles_forward import TOP_KEY

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

def evidence_rows(frozen,overlap,signed_rows,postmatch):
    """Preserve signed probabilities, exact identity and pending outcome separately."""
    def identity(r):
        return r["openligadb_match_id"],r["thesportsdb_event_id"]
    def index(rows):
        result={}
        for r in rows:
            k=identity(r)
            if k in result:raise ValueError("DUPLICATE_EVIDENCE_ID")
            result[k]=r
        return result
    expected=index(frozen["candidates"]);links=index(overlap["rows"]);results=index(postmatch["rows"])
    if set(expected)!=set(links) or set(expected)!=set(results):raise ValueError("EVIDENCE_COHORT_MISMATCH")
    out=[]
    for ident,c in expected.items():
        link=links[ident];result=results[ident]
        if result["kickoff_utc_recorded"]!=c["kickoff_utc_recorded"]:raise ValueError("RESULT_KICKOFF_CONFLICT")
        k=key({**c,"kickoff_utc":c["kickoff_utc_recorded"]})
        predictions=None;projection=None;model=None;protocol=None
        if link["state"]=="EXACT_NATIVE_ID_WITNESS_CANDIDATE":
            rows=[r for r in signed_rows if r["event_id"]=="openligadb:"+str(ident[0])]
            if len(rows)!=1 or key({**rows[0],"kickoff_utc":rows[0]["kickoff_utc_recorded"]})!=k:raise ValueError("SIGNED_ROW_CONFLICT")
            row=rows[0]
            predictions={name:row[name] for name in ("original","derived_rho0","candidate")}
            for values in predictions.values():
                if not isinstance(values,list) or len(values)!=3 or any(type(x) not in (float,int) or not math.isfinite(x) or not 0<=x<=1 for x in values) or abs(sum(values)-1)>.002:raise ValueError("INVALID_SIGNED_PROBABILITIES")
            projection=row["source_projection_sha256"];model=row["model_id"];protocol=row["protocol_sha256"]
        out.append({"openligadb_match_id":ident[0],"thesportsdb_event_id":ident[1],
            "league":c["league"],"home":c["home"],"away":c["away"],"kickoff_utc_recorded":c["kickoff_utc_recorded"],
            "witness_state":link["state"],"result_state":result["state"],"observed_scores":result["observed_scores"],
            "signed_probabilities_1x2":predictions,"signed_source_projection_sha256":projection,"model_id":model,"protocol_sha256":protocol,
            "actual_kickoff_authenticated":False,"regulation_time_authenticated":False,"source_independence_authenticated":False,
            "verified_forward_sample_credit":0})
    return {"schema":"forward-four-fixture-evidence-chain-v1","candidate_count":len(out),
        "signed_native_id_count":sum(r["signed_probabilities_1x2"] is not None for r in out),
        "result_states":dict(Counter(r["result_state"] for r in out)),
        "rows":out,"verified_forward_sample_credit":0,"production_recommendations":"DISABLED","status":"HOLD"}
def research_score(chain):
    """Descriptive same-fixture comparison only, never certified model scoring."""
    names=("original","derived_rho0","candidate")
    totals={k:{"correct":0,"log_loss":0.,"brier":0.} for k in names}
    excluded=Counter();seen=set();n=0
    for r in chain["rows"]:
        ident=(r["openligadb_match_id"],r["thesportsdb_event_id"])
        if ident in seen:raise ValueError("DUPLICATE_SCORE_ID")
        seen.add(ident)
        if r["witness_state"]!="EXACT_NATIVE_ID_WITNESS_CANDIDATE":
            excluded["NO_EXACT_WITNESS"]+=1;continue
        if r["result_state"]!="TWO_PUBLISHER_SCORE_AGREEMENT_UNVERIFIED":
            excluded[r["result_state"]]+=1;continue
        scores=r["observed_scores"]
        if not isinstance(scores,list) or len(scores)!=2 or scores[0]!=scores[1] or any(not isinstance(s,list) or len(s)!=2 or any(type(x) is not int or not 0<=x<=30 for x in s) for s in scores):raise ValueError("SCORE_AGREEMENT_CONFLICT")
        h,a=scores[0];y=0 if h>a else 1 if h==a else 2
        ps=r["signed_probabilities_1x2"]
        if not isinstance(ps,dict) or set(ps)!=set(names):raise ValueError("MISSING_SIGNED_VECTOR")
        for k in names:
            p=ps[k]
            if not isinstance(p,list) or len(p)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in p) or abs(sum(p)-1)>.002:raise ValueError("INVALID_SIGNED_PROBABILITIES")
            # Normalize rounded signed values only for metrics; preserve original bytes.
            p=[x/sum(p) for x in p]
            totals[k]["correct"]+=int(max(range(3),key=lambda i:p[i])==y)
            totals[k]["log_loss"]-=math.log(max(p[y],1e-15))
            totals[k]["brier"]+=sum((p[i]-int(i==y))**2 for i in range(3))
        n+=1
    return {"schema":"four-fixture-descriptive-score-v1","cohort_n":len(seen),"observed_agreement_n":n,
        "excluded":dict(excluded),"metrics":{k:{"n":n,"correct":v["correct"],"accuracy":v["correct"]/n,"log_loss":v["log_loss"]/n,"brier":v["brier"]/n} for k,v in totals.items()} if n else None,
        "same_fixture_denominator":True,"outcomes_independently_authenticated":False,
        "model_advantage_verified":False,"verified_forward_sample_credit":0,"production_recommendations":"DISABLED","status":"HOLD"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--proof",required=True);p.add_argument("--evidence-chain",action="store_true");p.add_argument("--primary");p.add_argument("--secondary");p.add_argument("--as-of");a=p.parse_args()
    frozen=audit(*(read(a.root,path) for path in BLOBS))
    report=witness.audit(Path(a.proof),source_sha="e5fd3e487a0eb18c955fe5a2d0c384fcf2222d08",workflow_sha="e5fd3e487a0eb18c955fe5a2d0c384fcf2222d08",run_id="45594300848",attempt="1")
    if not all(report.get(k) is True for k in ("audit_completed","signature_identity_and_subjects_verified","candidate_bytes_formula_source_binding_verified")) or report["total_candidates"]!=27 or len(report["cases"])!=27:raise ValueError("WITNESS_NOT_VERIFIED")
    out=join(frozen["candidates"],report["cases"]);out["verified_tlog_utc"]=report["verified_tlog_utc"];out["subject_sha256"]=report["subject_sha256"]
    if a.evidence_chain:
        if not all((a.primary,a.secondary,a.as_of)):raise ValueError("MISSING_EVIDENCE_INPUT")
        raw=witness.provenance._read(Path(a.proof)/"shadow.json",witness.provenance.MAX_FILE_BYTES)
        if hashlib.sha256(raw).hexdigest()!=report["subject_sha256"]["shadow.json"]:raise ValueError("SIGNED_SHADOW_CHANGED")
        signed=witness.provenance._json(raw)[TOP_KEY]["predictions"]
        primary,ph=read_later(a.primary);secondary,sh=read_later(a.secondary)
        post=compare(frozen,primary,secondary,stamp(a.as_of))
        out=evidence_rows(frozen,out,signed,post)
        out.update(verified_tlog_utc=report["verified_tlog_utc"],subject_sha256=report["subject_sha256"],source_commit=frozen["source_commit"],source_blobs=frozen["source_blobs"],postmatch_input_sha256={"primary":ph,"secondary":sh},checked_utc=post["checked_utc"])
    if a.evidence_chain:out["descriptive_score"]=research_score(out)
    print(json.dumps(out,allow_nan=False,sort_keys=True))
if __name__=="__main__":main()
