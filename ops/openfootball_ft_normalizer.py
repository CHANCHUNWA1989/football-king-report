"""Normalize OpenFootball downloaded FT candidates; never independently attest scores."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

def normalize(raw, source_url, captured_utc):
    payload=json.loads(raw)
    if not isinstance(payload,dict) or not isinstance(payload.get("matches"),list):
        raise ValueError("INVALID_OPENFOOTBALL_SCHEMA")
    captured=datetime.fromisoformat(captured_utc.replace("Z","+00:00"))
    if captured.tzinfo is None:
        raise ValueError("NAIVE_CAPTURE_TIME")
    rows=[]
    digest=hashlib.sha256(raw).hexdigest()
    for match in payload["matches"]:
        if not isinstance(match,dict):
            continue
        try:
            home=match["team1"]
            away=match["team2"]
            date=match["date"]
            score=match["score"]["ft"]
            if not isinstance(home,str) or not home.strip() or not isinstance(away,str) or not away.strip():
                continue
            if not isinstance(date,str) or len(date)!=10:
                continue
            datetime.strptime(date,"%Y-%m-%d")
            if not isinstance(score,list) or len(score)!=2 or any(type(v) is not int or not 0<=v<=30 for v in score):
                continue
            # OpenFootball may publish only a calendar date. Never invent a kickoff time.
            rows.append({"provider":"OpenFootball","home":home,"away":away,
                "match_date":date,"kickoff_utc":None,"score_ft":score,"status":"FT",
                "source_url":source_url,"raw_sha256":digest,
                "captured_utc":captured.astimezone(timezone.utc).isoformat(),
                "independently_verified":False,"kickoff_precision":"DATE_ONLY"})
        except (KeyError,TypeError,ValueError,AttributeError):
            continue
    return rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--raw",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    manifest=json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    entry=next((s for s in manifest.get("sources",[]) if s.get("provider")=="OpenFootball" and s.get("status")=="FETCHED_UNVERIFIED"),None)
    rows=[]
    if entry:
        raw=Path(a.raw).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry["raw_sha256"]:
            raise ValueError("RAW_DIGEST_MISMATCH")
        rows=normalize(raw,entry["source_url"],manifest["captured_utc"])
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({"schema":"football-king-openfootball-ft-candidates-v1",
        "status":"UNVERIFIED","independently_verified":False,
        "production_recommendations":"DISABLED","rows":rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":
    main()
