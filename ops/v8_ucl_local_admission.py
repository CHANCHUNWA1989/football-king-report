"""V8.6 authorized local UCL season snapshot admission; no credential access."""
import argparse
from collections import Counter
from datetime import datetime,timezone,timedelta
import hashlib,json
from pathlib import Path
from ops.v6_forward_bundle import decode
from ops.v5_ucl_source_gate import FD,ident,utc
from ops.v8_ucl_current_intake import fd_diagnostics,season_at,HK,score_pair

LIMIT=2_000_000
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):
    p=Path(path)
    if not 0<p.stat().st_size<=LIMIT:raise ValueError("SIZE")
    raw=p.read_bytes()
    return raw,decode(raw)
def map_ids(doc,teams):
    if doc.get("schema")!="v8-6-ucl-historical-label-map-v1" or not isinstance(doc.get("pairs"),list) or len(doc["pairs"])>36:raise ValueError("MAP_SCHEMA")
    result={};labels=set()
    for r in doc["pairs"]:
        native=ident(r["football_data_team_id"]);label=r["historical_label"]
        if native not in teams or native in result or not isinstance(label,str) or not 0<len(label.strip())<=109 or label in labels:raise ValueError("MAP_CONFLICT")
        url=r.get("evidence_reference")
        if not isinstance(url,str) or not url.startswith("https://") or len(url)>500:raise ValueError("MAP_EVIDENCE")
        result[native]=label;labels.add(label)
    return result
def admit(raw,meta,mapping,now):
    if now.utcoffset() is None:raise ValueError("NAIVE_CLOCK")
    if not 0<len(raw)<=LIMIT or meta.get("schema")!="v8-6-ucl-authorized-capture-v1" or meta.get("source")!=FD or meta.get("payload_sha256")!=sha(raw):raise ValueError("CAPTURE_INTEGRITY")
    year=season_at(now)
    if type(meta.get("season")) is not int or meta["season"]!=year:raise ValueError("SEASON")
    doc=decode(raw)
    diag=fd_diagnostics({"payload":doc,"captured_utc":meta["captured_utc"],"sha256":sha(raw)},now,year)
    rows=[r for r in doc["matches"] if r.get("stage") in ("LEAGUE_STAGE","REGULAR_SEASON","GROUP_STAGE")]
    teams={ident(r[k]["id"]) for r in rows for k in ("homeTeam","awayTeam")}
    ids=map_ids(mapping,teams)
    training=[];future=[];unmapped=Counter()
    for r in rows:
        ko=utc(r["utcDate"]);h=ident(r["homeTeam"]["id"]);a=ident(r["awayTeam"]["id"])
        if h not in ids or a not in ids:
            unmapped["unmapped_fixture"]+=1;continue
        item={"provider_event_id":ident(r["id"]),"home_native_id":h,"away_native_id":a,"kickoff_utc":ko.isoformat(),
              "home_historical_label":ids[h],"away_historical_label":ids[a]}
        if r["status"]=="FINISHED" and ko.astimezone(HK).date()<now.astimezone(HK).date():
            x,y=score_pair(r["score"]["fullTime"])
            training.append({**item,"score":[x,y]})
        elif r["status"] in ("SCHEDULED","TIMED") and now+timedelta(minutes=10)<ko<=now+timedelta(days=2):
            future.append(item)
    # Locally declared metadata and references are not proof of provider provenance or club identity.
    return {"schema":"v8-6-ucl-local-admission-v1","as_of_utc":now.isoformat(),"season":year,"source_diagnostics":diag,
        "mapped_teams":len(ids),"phase_teams":len(teams),"unmapped_fixtures":unmapped["unmapped_fixture"],
        "local_training_candidate_count":len(training),"local_future_candidate_count":len(future),
        "source_identity_independently_authenticated":False,"crosswalk_independently_verified":False,
        "current_training_ready":False,"qualified_model_inputs":0,"current_fixture_forecasts":0,
        "verified_forward_sample_credit":0,"production_recommendations":"DISABLED","status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("capture","metadata","mapping","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args()
    raw,_=read(a.capture);_,meta=read(a.metadata);_,mapping=read(a.mapping)
    result=admit(raw,meta,mapping,datetime.now(timezone.utc))
    with Path(a.output).open("x") as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,allow_nan=False))
if __name__=="__main__":main()
