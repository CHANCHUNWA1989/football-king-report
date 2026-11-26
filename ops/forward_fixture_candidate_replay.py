"""Offline candidate ID replay; no authenticated identity, forecast or result credit."""
import argparse
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from live_germany_guard import verify as verify_primary, stamp
from source_publish_guard import verify as verify_secondary
from team_identity import team_id

PIN="77c942f333405f4fa0be586b71413ad946045525"
BLOBS={"sources/live_germany_latest.json":"38da140a6223363002b52c8d30f1464f1c516b3e",
       "sources/latest.json":"3e9ec00cd75b2e51f97948734475345d1912a45a"}
def unique(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError("DUPLICATE_JSON_KEY")
        out[k]=v
    return out
def reject_constant(_):raise ValueError("NONFINITE_JSON")
def read(root,path):
    f=Path(root)/path
    if f.is_symlink() or not f.is_file() or not 0<f.stat().st_size<=500000:raise ValueError("INPUT_FILE")
    raw=f.read_bytes()
    if hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\x00"+raw).hexdigest()!=BLOBS[path]:raise ValueError("PINNED_BLOB_MISMATCH")
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject_constant)
def key(row):
    league=row["league"]
    h,a=team_id(league,row["home"]),team_id(league,row["away"])
    if not h or not a or h==a:raise ValueError("TEAM_KEY")
    return (league,h,a,stamp(row["kickoff_utc"]))
def audit(primary,secondary):
    now=stamp(primary["collected_utc"])
    verify_primary(primary,now=now)
    second=verify_secondary(secondary,now=now)
    if not timedelta(0)<=now-second<=timedelta(hours=36) or stamp(primary["schedule_crosscheck_time_utc"])!=second:raise ValueError("SOURCE_CLOCK")
    if primary.get("source_identity_independently_authenticated") is not False:raise ValueError("UNSAFE_IDENTITY")
    rows=[r for r in secondary["sampled_fixtures"] if r["provider"]=="thesportsdb"]
    pairs=[];seen=set()
    for r in primary["matches"]:
        link=r["source_id_pair"]
        if link is None:continue
        if r["status"]!="SCHEDULED" or r["score_ft"] is not None or key(r)[3]<=now:raise ValueError("NOT_PREMATCH")
        matches=[s for s in rows if key(s)==key(r)]
        if len(matches)!=1:raise ValueError("AMBIGUOUS_OR_MISSING_MATCH")
        s=matches[0];sid=s["provider_event_id"]
        if sid!=link["thesportsdb_event_id"] or sid in seen or s["status"]!="SCHEDULED" or s["score_ft"] is not None:raise ValueError("PAIR_CONFLICT")
        seen.add(sid)
        pairs.append({"league":r["league"],"home":r["home"],"away":r["away"],"kickoff_utc_recorded":key(r)[3].isoformat(),
          "openligadb_match_id":r["provider_match_id"],"thesportsdb_event_id":sid,"status":"LOOKUP_CANDIDATE_ONLY",
          "source_identity_authenticated":False,"actual_kickoff_authenticated":False,"forecast_witness_verified":False,"final_score_verified":False})
    if len(pairs)!=primary["unverified_provider_id_pairs"]:raise ValueError("PAIR_COUNT")
    return {"schema":"forward-fixture-candidate-replay-v1","primary_observed_utc":now.isoformat(),"secondary_observed_utc":second.isoformat(),
      "source_clock_gap_seconds":(now-second).total_seconds(),"primary_rows":len(primary["matches"]),"candidate_count":len(pairs),
      "not_paired_count":len(primary["matches"])-len(pairs),"candidates":pairs,"source_commit":PIN,"source_blobs":BLOBS,
      "verified_forward_sample_credit":0,"production_recommendations":"DISABLED","status":"HOLD"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);a=p.parse_args()
    r=audit(*(read(a.root,path) for path in BLOBS))
    if r["primary_rows"]!=28 or r["candidate_count"]!=4:raise ValueError("PINNED_COHORT_CHANGED")
    print(json.dumps(r,allow_nan=False,sort_keys=True))
if __name__=="__main__":main()
