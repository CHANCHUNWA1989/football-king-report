"""Multi-source historical research router. No live or EV qualification.

Public-domain OpenFootball historical results, or an authorized local
Football-Data CSV. Never replace a missing live feed with historical data.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from datetime import date,datetime
from pathlib import Path
from urllib.request import Request,build_opener,HTTPRedirectHandler
from research_strict_json import unique_object,reject_constant
from score_distribution_vnext import score_matrix,one_x_two

LIMIT=4_000_000
OPEN_URL="https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/mx.1.json"
OPEN_BLOB="01eb9b765c10372ad3dd5ebe8a2067bfc4376223"
SOURCE={
    "openfootball":("historical_results",),
    "football-data":("historical_results","historical_odds"),
    "statsbomb":("historical_events","historical_xg"),
    "strikerapi":("historical_results","historical_events","historical_xg","historical_odds"),
    "api-football":("live_state","live_xg","live_quotes"),
    "sportmonks":("live_state","live_xg","live_quotes"),
    "public_web":("manual_state_review",),
}


def blob(raw):
    return hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()


def checked(raw):
    if type(raw) is not bytes or not 0<len(raw)<=LIMIT:
        raise ValueError("INVALID_SIZE")
    return raw.decode("utf-8-sig")


def row(day,h,a,score):
    d=date.fromisoformat(day)
    if any(type(t) is not str or not t.strip() or len(t)>120 for t in (h,a)) or h.strip()==a.strip():
        raise ValueError("TEAM")
    if type(score) is not list or len(score)!=2 or any(type(x) is not int or not 0<=x<=30 for x in score):
        raise ValueError("SCORE")
    return (d.isoformat(),h.strip(),a.strip(),score[0],score[1])


def unique(rows):
    seen=set()
    for r in rows:
        if r[:3] in seen:
            raise ValueError("DUPLICATE_MATCH")
        seen.add(r[:3])
    return sorted(rows)


def openfootball(raw):
    data=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if type(data) is not dict or data.get("name")!="Liga MX 2024/25" or type(data.get("matches")) is not list:
        raise ValueError("OPENFOOTBALL_SCOPE")
    rows=[]
    for m in data["matches"]:
        score=m.get("score",{}).get("ft")
        if score is not None:
            r=row(m["date"],m["team1"],m["team2"],score)
            if not "2024-07-01"<=r[0]<"2025-07-01":
                raise ValueError("SEASON_DATE")
            rows.append(r)
    return unique(rows)


def football_data(raw):
    """Local authorized MEX.csv; results only, do not infer odds timestamps."""
    reader=csv.DictReader(io.StringIO(checked(raw)))
    fields=reader.fieldnames or []
    if len(fields)!=len(set(fields)) or not {"Country","League","Date","Home","Away","HG","AG"}<=set(fields):
        raise ValueError("CSV_SCHEMA")
    rows=[]
    for m in reader:
        if None in m or m["Country"]!="Mexico" or m["League"]!="Liga MX":
            raise ValueError("CSV_SCOPE")
        if not m["HG"] and not m["AG"]:
            continue
        if not all(type(m[k]) is str and m[k].isascii() and m[k].isdigit() for k in ("HG","AG")):
            raise ValueError("CSV_SCORE")
        dt=datetime.strptime(m["Date"],"%d/%m/%Y").date().isoformat()
        rows.append(row(dt,m["Home"],m["Away"],[int(m["HG"]),int(m["AG"])]))
    return unique(rows)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError("REDIRECT")


def fetch_openfootball():
    """One public request, no auth or retries; fixed path and byte pin."""
    with build_opener(NoRedirect()).open(Request(OPEN_URL,headers={"Accept":"application/json","User-Agent":"FootballKingResearch/1.0"}),timeout=15) as r:
        if r.geturl()!=OPEN_URL or r.status!=200:
            raise ValueError("HTTP_SOURCE")
        raw=r.read(LIMIT+1)
    if len(raw)>LIMIT or blob(raw)!=OPEN_BLOB:
        raise ValueError("PUBLIC_BLOB_CHANGED")
    return raw


def baseline(rows):
    """One frozen league mean from preceding match dates, no same-day leakage."""
    n=0;gh=ga=0;loss=[];brier=[]
    for day in sorted({r[0] for r in rows}):
        batch=[r for r in rows if r[0]==day]
        if n>=50:
            h=max(.1,min(5.5,gh/n));a=max(.1,min(5.5,ga/n))
            p=one_x_two(score_matrix(h,a))
            for _,_,_,x,y in batch:
                k="HOME" if x>y else "DRAW" if x==y else "AWAY"
                loss.append(-math.log(max(1e-15,p[k])))
                brier.append(sum((v-(i==k))**2 for i,v in p.items()))
        n+=len(batch);gh+=sum(r[3] for r in batch);ga+=sum(r[4] for r in batch)
    return {"finished_matches":n,"historical_assessment_n":len(loss),
            "log_loss":math.fsum(loss)/len(loss) if loss else None,
            "brier":math.fsum(brier)/len(brier) if brier else None,
            "historically_reconstructed":True,"verified_forward_sample_credit":0}


def route(purpose,candidates):
    """Candidates are (source, zero-argument byte loader); only two implemented
    historical result readers execute. No fallback to stale data for live tasks.
    """
    out={"status":"HOLD","production_recommendations":"DISABLED",
         "source_authenticated":False,"actual_live_odds_verified":False,
         "positive_ev_verified":False,"verified_forward_sample_credit":0,"attempts":[]}
    if purpose!="historical_results":
        return {**out,"reason":"NO_QUALIFIED_IMPLEMENTED_SOURCE_FOR_PURPOSE"}
    if type(candidates) is not list or len(candidates)>2:
        return {**out,"reason":"CANDIDATE_LIMIT"}
    seen=set()
    for name,load in candidates:
        if name in seen or name not in ("openfootball","football-data"):
            continue
        seen.add(name)
        try:
            raw=load()
            rows=(openfootball if name=="openfootball" else football_data)(raw)
            if not rows:
                raise ValueError("EMPTY_RESULTS")
            return {**out,"reason":"HISTORICAL_RESEARCH_ONLY","source":name,
                    "sha256":hashlib.sha256(raw).hexdigest(),
                    "metrics":baseline(rows)}
        except (ValueError,TypeError,KeyError,AttributeError,OSError,OverflowError,RecursionError):
            out["attempts"].append({"source":name,"reason":"UNAVAILABLE_OR_INVALID"})
    return {**out,"reason":"NO_VALID_HISTORICAL_SOURCE"}


def local(path):
    with Path(path).open("rb") as f:
        return f.read(LIMIT+1)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--open-public",action="store_true",help="one fixed public-domain read")
    p.add_argument("--local-mex-csv",help="authorized private local CSV")
    a=p.parse_args()
    c=[]
    if a.open_public:
        c.append(("openfootball",fetch_openfootball))
    if a.local_mex_csv:
        c.append(("football-data",lambda:local(a.local_mex_csv)))
    out=route("historical_results",c)
    print(json.dumps(out,sort_keys=True,allow_nan=False))
    return 0 if out.get("source") else 1


if __name__=="__main__":
    raise SystemExit(main())
