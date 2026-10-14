"""Fail-closed, non-scoring global league coverage report from raw manifests."""
import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from shadow_global_source_collector import LEAGUES,BASE

def summarize(folder):
    root=Path(folder)
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("status")!="HOLD" or manifest.get("independently_verified") is not False
        or manifest.get("production_recommendations")!="DISABLED"
        or manifest.get("eligible_for_model_scoring") is not False
        or manifest.get("source_independence")!="SINGLE_PUBLISHER"):
        raise ValueError("UNSAFE_GLOBAL_MANIFEST")
    year=manifest.get("season_start")
    if type(year) is not int or not 2000<=year<=2100:
        raise ValueError("INVALID_SEASON")
    captured=manifest.get("captured_utc")
    try:
        dt=datetime.fromisoformat(captured.replace("Z","+00:00"))
        if dt.tzinfo is None or dt.utcoffset().total_seconds()!=0:
            raise ValueError("INVALID_CAPTURE_TIME")
    except (AttributeError,TypeError,ValueError):
        raise ValueError("INVALID_CAPTURE_TIME")
    rows=manifest.get("leagues")
    if not isinstance(rows,list) or len(rows)!=len(LEAGUES):
        raise ValueError("INCOMPLETE_LEAGUE_COVERAGE")
    seen=set()
    report=[]
    season=f"{year}-{str(year+1)[-2:]}"
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("INVALID_LEAGUE_ROW")
        league=row.get("league")
        if league not in LEAGUES or league in seen:
            raise ValueError("UNKNOWN_OR_DUPLICATE_LEAGUE")
        seen.add(league)
        expected=f"{BASE}/{season}/{LEAGUES[league]}.json"
        if row.get("provider")!="OpenFootball" or row.get("source_url")!=expected:
            raise ValueError("UNTRUSTED_GLOBAL_SOURCE")
        status=row.get("status")
        count=0
        if status=="FETCHED_UNVERIFIED":
            if row.get("raw_file")!=league+".json":
                raise ValueError("UNSAFE_GLOBAL_RAW_FILE")
            raw=(root/(league+".json")).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row.get("raw_sha256"):
                raise ValueError("GLOBAL_RAW_HASH_MISMATCH")
            payload=json.loads(raw)
            if not isinstance(payload,dict) or not isinstance(payload.get("matches"),list):
                raise ValueError("INVALID_GLOBAL_RAW_SCHEMA")
            count=len(payload["matches"])
            if row.get("raw_matches")!=count:
                raise ValueError("GLOBAL_MATCH_COUNT_MISMATCH")
        elif status!="ERROR":
            raise ValueError("UNKNOWN_GLOBAL_SOURCE_STATUS")
        report.append({"league":league,"status":status,"raw_matches":count,
                       "verified_results":0,"eligible_for_scoring":False})
    return {"status":"HOLD","production_recommendations":"DISABLED",
            "independently_verified":False,"eligible_for_model_scoring":False,
            "source_independence":"SINGLE_PUBLISHER","season_start":year,
            "successful_leagues":sum(x["status"]=="FETCHED_UNVERIFIED" for x in report),
            "leagues":report}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--raw-dir",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=summarize(a.raw_dir)
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("GLOBAL SOURCE COVERAGE",result["successful_leagues"],"/",len(result["leagues"]),
          "verified results 0 (single publisher)")

if __name__=="__main__":
    main()
