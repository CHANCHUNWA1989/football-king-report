"""Compare later sanitized observations against frozen pre-match ID candidates.
No authentication, no forecast reconstruction and no certified settlement.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
from forward_fixture_candidate_replay import BLOBS, read, audit, key, stamp, unique, reject_constant, verify_primary, verify_secondary

def read_later(path):
    f=Path(path)
    if f.is_symlink() or not f.is_file():raise ValueError("INPUT_FILE")
    with f.open("rb") as stream:raw=stream.read(500001)
    if not 0<len(raw)<=500000:raise ValueError("INPUT_SIZE")
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject_constant),hashlib.sha256(raw).hexdigest()

def compare(frozen,primary,secondary,now):
    if now.utcoffset() is None:raise ValueError("AUDIT_CLOCK")
    ptime=stamp(primary["collected_utc"])
    stime=stamp(secondary["collected_utc"])
    if max(ptime,stime)>now:raise ValueError("FUTURE_CAPTURE")
    verify_primary(primary,now=ptime)
    verify_secondary(secondary,now=stime)
    if ptime<stamp(frozen["primary_observed_utc"]) or stime<stamp(frozen["secondary_observed_utc"]):raise ValueError("CAPTURE_REGRESSION")
    results=[]
    for c in frozen["candidates"]:
        fixture={**c,"kickoff_utc":c["kickoff_utc_recorded"]}
        k=key(fixture);ko=k[3]
        pp=[r for r in primary["matches"] if r["provider_match_id"]==c["openligadb_match_id"]]
        ss=[r for r in secondary["sampled_fixtures"] if r["provider"]=="thesportsdb" and r["provider_event_id"]==c["thesportsdb_event_id"]]
        status="AWAITING_RECORDED_KICKOFF_PLUS_2H";scores=None
        if len(pp)>1 or len(ss)>1:status="AMBIGUOUS_ID"
        elif any(key(r)!=k for r in pp+ss):status="IDENTITY_OR_KICKOFF_CONFLICT"
        elif now>=ko+timedelta(hours=2):
            if not pp or not ss:status="MISSING_SOURCE_ROW"
            elif min(ptime,stime)<ko+timedelta(hours=2):status="AWAITING_POSTMATCH_CAPTURE"
            elif pp[0]["status"]!="FINISHED_CONFIRMED_BY_SOURCE" or ss[0]["status"]!="FINISHED" or pp[0]["score_ft"] is None or ss[0]["score_ft"] is None:status="AWAITING_BOTH_FINAL_SCORES"
            else:
                scores=[pp[0]["score_ft"],ss[0]["score_ft"]]
                status="TWO_PUBLISHER_SCORE_AGREEMENT_UNVERIFIED" if scores[0]==scores[1] else "SCORE_CONFLICT"
        results.append({"openligadb_match_id":c["openligadb_match_id"],"thesportsdb_event_id":c["thesportsdb_event_id"],"kickoff_utc_recorded":ko.isoformat(),"state":status,"observed_scores":scores,
            "actual_kickoff_authenticated":False,"regulation_time_authenticated":False,"forecast_witness_verified":False,"source_independence_authenticated":False,"verified_forward_sample_credit":0})
    return {"schema":"forward-fixture-postmatch-diagnostic-v1","candidate_count":len(results),"counts":dict(Counter(r["state"] for r in results)),
      "primary_observed_utc":ptime.isoformat(),"secondary_observed_utc":stime.isoformat(),"checked_utc":now.isoformat(),
      "rows":results,"verified_forward_sample_credit":0,"production_recommendations":"DISABLED","status":"HOLD"}

def main():
    p=argparse.ArgumentParser()
    for k in ("root","primary","secondary"):p.add_argument("--"+k,required=True)
    p.add_argument("--as-of");a=p.parse_args()
    frozen=audit(*(read(a.root,path) for path in BLOBS))
    primary,ph=read_later(a.primary);secondary,sh=read_later(a.secondary)
    now=stamp(a.as_of) if a.as_of else datetime.now(timezone.utc)
    out=compare(frozen,primary,secondary,now);out["input_sha256"]={"primary":ph,"secondary":sh}
    print(json.dumps(out,allow_nan=False,sort_keys=True))
if __name__=="__main__":main()
