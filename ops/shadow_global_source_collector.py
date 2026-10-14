"""Research-only multi-league OpenFootball raw snapshot collector.

Single publisher coverage is never independent FT verification or model scoring.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from shadow_raw_source_collector import fetch

LEAGUES={
    "eng-premier":"en.1",
    "eng-championship":"en.2",
    "esp-laliga":"es.1",
    "ita-seriea":"it.1",
    "fra-ligue1":"fr.1",
    "ger-bundesliga":"de.1",
}
BASE="https://raw.githubusercontent.com/openfootball/football.json/master"

def collect(year,outdir,getter=fetch,now=None):
    if type(year) is not int or not 2000<=year<=2100:
        raise ValueError("INVALID_SEASON")
    captured=now or datetime.now(timezone.utc)
    if not isinstance(captured,datetime) or captured.tzinfo is None:
        raise ValueError("INVALID_CAPTURE_TIME")
    out=Path(outdir)
    out.mkdir(parents=True,exist_ok=True)
    season=f"{year}-{str(year+1)[-2:]}"
    manifest={"schema":"football-king-global-raw-research-v1",
              "season_start":year,"captured_utc":captured.astimezone(timezone.utc).isoformat(),
              "status":"HOLD","independently_verified":False,
              "production_recommendations":"DISABLED","eligible_for_model_scoring":False,
              "source_independence":"SINGLE_PUBLISHER","leagues":[]}
    for league,code in LEAGUES.items():
        url=f"{BASE}/{season}/{code}.json"
        row={"league":league,"provider":"OpenFootball","source_url":url,"status":"ERROR"}
        try:
            raw=getter(url)
            payload=json.loads(raw)
            if not isinstance(payload,dict) or not isinstance(payload.get("matches"),list):
                raise ValueError("INVALID_MATCH_SCHEMA")
            name=league+".json"
            (out/name).write_bytes(raw)
            row.update(status="FETCHED_UNVERIFIED",raw_file=name,
                       raw_sha256=hashlib.sha256(raw).hexdigest(),
                       bytes=len(raw),raw_matches=len(payload["matches"]))
        except (OSError,ValueError,TypeError,TimeoutError) as exc:
            row["error_type"]=type(exc).__name__
            if hasattr(exc,"code"):row["http_status"]=int(exc.code)
        manifest["leagues"].append(row)
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--year",type=int,required=True)
    p.add_argument("--output-dir",required=True)
    a=p.parse_args()
    result=collect(a.year,a.output_dir)
    print("GLOBAL RESEARCH ONLY",[(x["league"],x["status"]) for x in result["leagues"]])

if __name__=="__main__":
    main()
