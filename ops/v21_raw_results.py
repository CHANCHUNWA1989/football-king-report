"""V21 bounded raw capture and explicit Bundesliga native-ID result crosswalk.
No inferred team identity, automatic credential access or evidence credit.
"""
import argparse
import json
import os
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.request import Request,build_opener,HTTPRedirectHandler
from ops.v6_forward_bundle import decode,digest,utc,native
from ops.v20_signed_receipts import sha,bounded,exact
from ops.v5_native_bundesliga_forward import normalize

LIMIT=3_000_000
URLS={"openligadb":"https://api.openligadb.de/getmatchdata/bl1/",
      "football-data.org":"https://api.football-data.org/v4/competitions/BL1/matches?season="}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*a,**k):raise ValueError("REDIRECT_REFUSED")

def capture(provider,season,*,token=None):
    if provider not in URLS or type(season) is not int or not 2020<=season<=2035:
        raise ValueError("CAPTURE_SCOPE")
    if provider=="football-data.org" and (not isinstance(token,str) or not token):
        raise ValueError("OWNER_TOKEN_REQUIRED")
    headers={"Accept":"application/json","User-Agent":"FootballKingResearch/21.0"}
    if provider=="football-data.org":headers["X-Auth-Token"]=token
    url=URLS[provider]+str(season)
    with build_opener(NoRedirect()).open(Request(url,headers=headers),timeout=15) as resp:
        raw=resp.read(LIMIT+1)
    bounded(raw,LIMIT);decode(raw)
    now=datetime.now(timezone.utc)
    return raw,{"provider":provider,"season":season,"source":url,"captured_utc":now.isoformat(),
                "sha256":sha(raw),"bytes":len(raw),"source_authenticated":False}

def crosswalk(raw,expected,ko):
    bounded(raw,100000)
    if sha(raw)!=digest(expected):raise ValueError("CROSSWALK_DIGEST")
    d=exact(decode(raw),("schema","season","frozen_utc","pairs"))
    if d["schema"]!="v21-bl1-crosswalk-v1" or type(d["season"]) is not int or d["season"]!=ko.year-int(ko.month<7) or utc(d["frozen_utc"])>=ko-timedelta(minutes=10):
        raise ValueError("CROSSWALK_CLOCK_SCOPE")
    if type(d["pairs"]) is not list or not 2<=len(d["pairs"])<=18:raise ValueError("CROSSWALK_SIZE")
    m={};used=set()
    for row in d["pairs"]:
        exact(row,("openligadb_team_id","football_data_team_id","evidence_reference"))
        a,b=map(native,(row["openligadb_team_id"],row["football_data_team_id"]))
        if a in m or b in used or not isinstance(row["evidence_reference"],str) or not row["evidence_reference"].startswith("https://"):
            raise ValueError("CROSSWALK_CONFLICT")
        m[a]=b;used.add(b)
    return m

def score(x,y):
    if any(type(z) is not int or not 0<=z<=20 for z in (x,y)):raise ValueError("FINAL_SCORE")
    return (x,y)

def verify_result(raw,provider,*,fixture_id,home_id,away_id,kickoff_utc,observed_utc,mapping_raw=None,mapping_sha256=None):
    bounded(raw,LIMIT);ko,obs=map(utc,(kickoff_utc,observed_utc))
    mid,h,a=map(native,(fixture_id,home_id,away_id))
    if h==a or obs<ko+timedelta(hours=2):raise ValueError("RESULT_CLOCK_IDENTITY")
    year=ko.year-int(ko.month<7)
    doc=decode(raw)
    if provider=="openligadb":
        normalize(doc,year,obs,shortcut="bl1")
        rows=[r for r in doc if str(r["matchID"])==mid]
        if len(rows)!=1:raise ValueError("RESULT_EVENT_MISSING")
        r=rows[0]
        if (str(r["team1"]["teamId"]),str(r["team2"]["teamId"]),utc(r["matchDateTimeUTC"]))!=(h,a,ko) or r["matchIsFinished"] is not True:
            raise ValueError("RESULT_IDENTITY_STATE")
        ft=[z for z in r["matchResults"] if z["resultTypeID"]==2]
        if len(ft)!=1:raise ValueError("RESULT_FINAL")
        return {"provider_event_id":mid,"score":score(ft[0]["pointsTeam1"],ft[0]["pointsTeam2"])}
    if provider!="football-data.org":raise ValueError("PROVIDER_UNSUPPORTED")
    m=crosswalk(mapping_raw,mapping_sha256,ko)
    if h not in m or a not in m:raise ValueError("CROSSWALK_MISSING_TEAM")
    if type(doc) is not dict or doc.get("competition",{}).get("code")!="BL1" or type(doc.get("matches")) is not list or len(doc["matches"])>400:
        raise ValueError("RESULT_COMPETITION")
    seen=set();matched=[]
    for r in doc["matches"]:
        if r.get("competition",{}).get("code")!="BL1" or r.get("season",{}).get("startDate","")[:4]!=str(year):
            raise ValueError("RESULT_SEASON")
        event=native(str(r["id"]));rh=native(str(r["homeTeam"]["id"]));ra=native(str(r["awayTeam"]["id"]))
        if event in seen or rh==ra:raise ValueError("RESULT_DUPLICATE")
        seen.add(event)
        if (rh,ra)==(m[h],m[a]) and utc(r["utcDate"])==ko:matched.append(r)
    if len(matched)!=1:raise ValueError("RESULT_EVENT_MISSING_OR_AMBIGUOUS")
    r=matched[0];s=r["score"]
    if r["status"]!="FINISHED" or s.get("duration")!="REGULAR":raise ValueError("RESULT_FINAL")
    return {"provider_event_id":str(r["id"]),"score":score(s["fullTime"]["home"],s["fullTime"]["away"])}

def compare(open_raw,fd_raw,*,fixture_id,home_id,away_id,kickoff_utc,open_observed_utc,fd_observed_utc,mapping_raw,mapping_sha256):
    common=dict(fixture_id=fixture_id,home_id=home_id,away_id=away_id,kickoff_utc=kickoff_utc)
    x=verify_result(open_raw,"openligadb",observed_utc=open_observed_utc,**common)
    y=verify_result(fd_raw,"football-data.org",observed_utc=fd_observed_utc,mapping_raw=mapping_raw,mapping_sha256=mapping_sha256,**common)
    if x["score"]!=y["score"]:raise ValueError("DUAL_RESULT_CONFLICT")
    return {"schema":"v21-dual-raw-result-research-v1","fixture_id":fixture_id,"score":list(x["score"]),
        "provider_events":{"openligadb":x["provider_event_id"],"football-data.org":y["provider_event_id"]},
        "raw_sha256":[sha(open_raw),sha(fd_raw)],"crosswalk_sha256":mapping_sha256,
        "raw_score_semantics_checked":True,"source_independence_verified":False,"crosswalk_independently_verified":False,
        "capture_clock_attested":False,"verified_forward_sample_credit":0,"production_recommendations":"DISABLED","status":"HOLD"}

def audit_signed_fixture(archive,policy_raw,policy_sha256,witness,results,*,fixture_id,as_of_utc,mapping_raw,mapping_sha256):
    """Require both cryptographic and provider-semantic checks.
    V20 policy must identify the two result origins by the exact provider labels.
    Crosswalk provenance and actual source independence remain external.
    """
    from ops.v20_signed_receipts import audit_fixture
    proof=audit_fixture(archive,policy_raw,policy_sha256,witness,results,
                        fixture_id=fixture_id,as_of_utc=as_of_utc)
    docs={}
    for payload,_,raw in results:
        q=decode(payload)
        if q["origin"] not in URLS or q["origin"] in docs:raise ValueError("RESULT_PROVIDER_ROLE")
        docs[q["origin"]]=(q,raw)
    if set(docs)!=set(URLS):raise ValueError("RESULT_PROVIDER_ROLE")
    left,lr=docs["openligadb"];right,rr=docs["football-data.org"]
    data=compare(lr,rr,fixture_id=fixture_id,home_id=left["home_native_id"],
        away_id=left["away_native_id"],kickoff_utc=left["kickoff_utc"],
        open_observed_utc=left["observed_utc"],fd_observed_utc=right["observed_utc"],
        mapping_raw=mapping_raw,mapping_sha256=mapping_sha256)
    if data["score"]!=proof["claimed_final_score"]:raise ValueError("SIGNED_RAW_SCORE_CONFLICT")
    return {**proof,"schema":"v21-signed-dual-raw-result-research-v1",
            "raw_result_semantic_audit":data,"verified_forward_sample_credit":0}

def main():
    p=argparse.ArgumentParser();p.add_argument("--provider",choices=tuple(URLS),required=True)
    p.add_argument("--season",type=int,required=True);p.add_argument("--output-dir",required=True)
    a=p.parse_args()
    # Explicit invocation only; do not print token or raw content.
    token=os.environ.get("FOOTBALL_DATA_ORG_TOKEN") if a.provider=="football-data.org" else None
    root=Path(a.output_dir);root.mkdir(mode=0o700,parents=False,exist_ok=False)
    raw,meta=capture(a.provider,a.season,token=token)
    for name,data in (("raw.json",raw),("receipt.json",json.dumps(meta,indent=2).encode())):
        fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as f:f.write(data)
    print(json.dumps({**meta,"verified_forward_sample_credit":0,"production_recommendations":"DISABLED","status":"HOLD"}))
if __name__=="__main__":main()
