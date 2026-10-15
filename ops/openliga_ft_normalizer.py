"""Parse downloaded OpenLigaDB FT candidates, without independent verification."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

def normalize(raw, source_url, captured_utc):
    payload=json.loads(raw)
    if not isinstance(payload,list):
        raise ValueError("INVALID_OPENLIGA_SCHEMA")
    stamp=datetime.fromisoformat(captured_utc.replace("Z","+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_CAPTURE_TIME")
    digest=hashlib.sha256(raw).hexdigest()
    rows=[]
    for match in payload:
        if not isinstance(match,dict) or match.get("matchIsFinished") is not True:
            continue
        try:
            home=match["team1"]["teamName"]
            away=match["team2"]["teamName"]
            kickoff=match["matchDateTimeUTC"]
            results=match["matchResults"]
            if not isinstance(home,str) or not home.strip() or not isinstance(away,str) or not away.strip():
                continue
            dt=datetime.fromisoformat(kickoff.replace("Z","+00:00"))
            if dt.tzinfo is None or dt.astimezone(timezone.utc)>stamp.astimezone(timezone.utc):
                continue
            fulltime=[r for r in results if isinstance(r,dict) and r.get("resultTypeID")==2]
            if len(fulltime)!=1:
                continue
            score=[fulltime[0]["pointsTeam1"],fulltime[0]["pointsTeam2"]]
            if any(type(v) is not int or not 0<=v<=30 for v in score):
                continue
            rows.append({"provider":"OpenLigaDB","provider_match_id":match.get("matchID"),
                "home":home,"away":away,"kickoff_utc":dt.astimezone(timezone.utc).isoformat(),
                "score_ft":score,"status":"FT","source_url":source_url,
                "raw_sha256":digest,"captured_utc":stamp.astimezone(timezone.utc).isoformat(),
                "independently_verified":False})
        except (KeyError,TypeError,ValueError,AttributeError):
            continue
    return rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--raw",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    manifest=json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    entry=next((x for x in manifest.get("sources",[]) if x.get("provider")=="OpenLigaDB" and x.get("status")=="FETCHED_UNVERIFIED"),None)
    rows=[]
    if entry:
        raw=Path(args.raw).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry["raw_sha256"]:
            raise ValueError("RAW_DIGEST_MISMATCH")
        rows=normalize(raw,entry["source_url"],manifest["captured_utc"])
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({"schema":"football-king-openliga-ft-candidates-v1",
        "status":"UNVERIFIED","independently_verified":False,
        "production_recommendations":"DISABLED","rows":rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":
    main()
