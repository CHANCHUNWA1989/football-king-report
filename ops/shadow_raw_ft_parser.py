"""Parse raw Bundesliga feeds into auditable, still-unverified FT candidates.

Raw publisher payloads are never treated as independently verified results.
"""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

def parse_openligadb(payload):
    if not isinstance(payload,list): raise ValueError("INVALID_OPENLIGADB")
    out=[]
    for m in payload:
        if not isinstance(m,dict) or not m.get("matchIsFinished"):continue
        try:
            scores=m["matchResults"]
            finals=[x for x in scores if x.get("resultTypeID")==2]
            if len(finals)!=1:continue
            ft=finals[0]
            goals=[ft["pointsTeam1"],ft["pointsTeam2"]]
            if any(type(x) is not int or x<0 or x>30 for x in goals):continue
            stamp=m["matchDateTimeUTC"]
            if not isinstance(stamp,str):continue
            ko=datetime.fromisoformat(stamp.replace("Z","+00:00"))
            if ko.tzinfo is None:ko=ko.replace(tzinfo=timezone.utc)
            if ko.utcoffset().total_seconds()!=0:continue
            out.append({"home":m["team1"]["teamName"],"away":m["team2"]["teamName"],
                "kickoff_utc":ko.isoformat().replace("+00:00","Z"),
                "score_ft":goals,"status":"FINISHED"})
        except (KeyError,TypeError,AttributeError,ValueError,OverflowError):continue
    return out

def parse_openfootball(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get("matches"),list):raise ValueError("INVALID_OPENFOOTBALL")
    out=[]
    for m in payload["matches"]:
        if not isinstance(m,dict):continue
        try:
            score=m["score"]["ft"]
            if not isinstance(score,list) or len(score)!=2 or any(type(x) is not int or x<0 or x>30 for x in score):continue
            out.append({"home":m["team1"],"away":m["team2"],"date":m["date"],
                        "score_ft":score,"status":"FINISHED"})
        except (KeyError,TypeError):continue
    return out

def convert(folder):
    folder=Path(folder)
    manifest=json.loads((folder/"manifest.json").read_text())
    if manifest.get("status")!="HOLD" or manifest.get("independently_verified") is not False:
        raise ValueError("UNSAFE_MANIFEST")
    out=[]
    seen=set()
    from shadow_raw_source_collector import URLS
    from shadow_verified_adapter import trusted_origin
    year=manifest.get("season_start")
    if type(year) is not int or not 2000<=year<=2100:
        raise ValueError("INVALID_MANIFEST_SEASON")
    parsers={"OpenLigaDB":parse_openligadb,"OpenFootball":parse_openfootball}
    sources=manifest.get("sources")
    if not isinstance(sources,list) or len(sources)>len(parsers):
        raise ValueError("INVALID_SOURCE_LIST")
    for source in sources:
        if not isinstance(source,dict):
            raise ValueError("INVALID_SOURCE_ENTRY")
        if source.get("status")!="FETCHED_UNVERIFIED":
            if source.get("status")!="ERROR":
                raise ValueError("UNKNOWN_SOURCE_STATUS")
            continue
        provider=source["provider"]
        if provider not in parsers:continue
        if provider in seen:raise ValueError("DUPLICATE_SOURCE_PROVIDER")
        seen.add(provider)
        expected_url=URLS[provider].format(year=year,next_year=year+1,short_next_year=str(year+1)[-2:])
        if source.get("source_url")!=expected_url or not trusted_origin(provider,source.get("source_url")):
            raise ValueError("SOURCE_URL_MISMATCH")
        expected_file=provider.lower()+".json"
        if source.get("raw_file")!=expected_file:
            raise ValueError("UNSAFE_RAW_FILE_PATH")
        raw=(folder/expected_file).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source["raw_sha256"]:
            raise ValueError("RAW_HASH_MISMATCH")
        records=parsers[provider](json.loads(raw))
        out.append({"provider":provider,"source_url":source["source_url"],
                    "raw_sha256":source["raw_sha256"],"captured_utc":manifest["captured_utc"],
                    "records":records,"independently_verified":False})
    return {"status":"HOLD","production_recommendations":"DISABLED",
            "sources":out,"independently_verified":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--raw-dir",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    Path(a.output).write_text(json.dumps(convert(a.raw_dir),ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
