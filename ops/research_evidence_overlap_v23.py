"""Join fresh forecast witnesses with historical result candidates, without promotion."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from .research_live_intake_v4 import MAX_BYTES
from .research_forecast_proof_locator_v19 import locate,scan
from .research_forecast_batch_v22 import batch
from .research_german_archive_discovery_v18 import extend
from .research_missing_fixture_discovery_v16 import candidates
from .research_archive_score_recovery_v14 import archive_snapshots
from .research_two_publisher_recovery_v15 import secondary_snapshots

STATES=("ONE_PUBLISHER_OUTCOME_AGREEMENT","TWO_PUBLISHER_SCORE_AGREEMENT")
def join(raw,result,proof):
    sha=hashlib.sha256(raw).hexdigest()
    if result["ledger_sha256"]!=sha or proof["ledger_sha256"]!=sha:
        raise ValueError("ledger binding mismatch")
    rows={r["key"]:r for r in candidates(raw).values()}
    cases=result["cases"]
    by_key={r["key"]:r for r in cases}
    if len(cases)!=len(by_key) or set(by_key)!=set(rows):
        raise ValueError("result roster mismatch")
    keys=proof["witness_keys"]
    if not isinstance(keys,list) or any(not isinstance(x,str) for x in keys):
        raise ValueError("invalid witness roster")
    witnessed=set(keys)
    if (len(keys)!=len(witnessed) or not witnessed.issubset(rows)
            or len(witnessed)!=proof["unique_witness_before_recorded_kickoff_count"]):
        raise ValueError("witness roster mismatch")
    matrix=Counter()
    for k,r in by_key.items():
        if r["league"]!=rows[k]["league"] or r.get("authenticated") is not False:
            raise ValueError("unsafe historical case")
        matrix[(r["state"],k in witnessed)]+=1
    def count(states):
        return sum(n for (s,w),n in matrix.items() if w and s in states)
    return {"schema":"unified-witness-result-overlap-v23","status":"HOLD",
        "production_recommendations":"DISABLED","ledger_sha256":sha,
        "ledger_rows":len(rows),"witnessed_before_recorded_kickoff":len(witnessed),
        "witness_and_result_corroboration":count(STATES),
        "witness_and_two_publisher_exact_score":count((STATES[1],)),
        "matrix":[{"result_state":s,"witnessed":w,"n":n} for (s,w),n in sorted(matrix.items())],
        "forecast_batch_passed":proof["batch_passed"],"authenticated_samples":0,
        "actual_kickoff_authenticated":False,"upstream_independence_proven":False,
        "model_promotion_allowed":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path("."))
    a=p.parse_args()
    with (a.root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    now=datetime.now(timezone.utc).isoformat()
    rows=candidates(raw)
    german={k:r for k,r in rows.items() if k[0]=="bundesliga"}
    result=extend(raw,archive_snapshots(a.root/"sources/live_germany/history",german),
        secondary_snapshots(a.root/"sources/history",rows),as_of=now)
    root=a.root/"forecast_provenance"
    locator=locate(raw,scan(root,raw),as_of=now)
    proof=batch(raw,root,locator,include_witness_keys=True)
    candidate_keys={c['key'] for c in locator['cases'] if c['state']=='MATCHING_PROOF_INPUT_CANDIDATE'}
    missing=sorted(candidate_keys-set(proof['witness_keys']))
    print('V22_MISSING_WITNESS_KEYS '+json.dumps({'ledger_sha256':proof['ledger_sha256'],
        'missing_keys':missing,'count':len(missing),'status':'HOLD',
        'production_recommendations':'DISABLED'},sort_keys=True,allow_nan=False))
    public={k:v for k,v in proof.items() if k!="witness_keys"}
    print("V22_BATCH_VERIFICATION_SUMMARY "+json.dumps(public,sort_keys=True,allow_nan=False))
    report=join(raw,result,proof)
    print("V23_EVIDENCE_OVERLAP_SUMMARY "+json.dumps(report,sort_keys=True,allow_nan=False))
    if not report["forecast_batch_passed"]:
        print("V25_WITNESSED_DIAGNOSTICS_SKIPPED INCOMPLETE_FRESH_VERIFICATION")
        return 2
    from .research_witnessed_model_diagnostics_v24 import diagnose
    diagnostic=diagnose(raw,result,proof)
    print("V25_WITNESSED_DIAGNOSTICS_SUMMARY "+json.dumps(diagnostic,sort_keys=True,allow_nan=False))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
