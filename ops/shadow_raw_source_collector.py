"""Fetch auditable OpenLigaDB and OpenFootball Bundesliga source responses.

This is a *candidate* collector, not independent result attestation. Raw bytes
are retained beside SHA256 digests; no invented scores, timestamps or URLs.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

URLS = {
    "OpenLigaDB": "https://api.openligadb.de/getmatchdata/bl1/{year}",
    "OpenFootball": "https://raw.githubusercontent.com/openfootball/football.json/master/{year}-{short_next_year}/de.1.json",
}

def fetch(url, opener=urlopen):
    request=Request(url,headers={"User-Agent":"football-king-shadow-research/1.0","Accept":"application/json"})
    with opener(request,timeout=20) as response:
        body=response.read(3_000_001)
        if len(body)>3_000_000:
            raise ValueError("SOURCE_TOO_LARGE")
    return body

def collect(year, outdir, getter=fetch, now=None):
    if type(year) is not int or not 2000 <= year <= 2100:
        raise ValueError("INVALID_SEASON")
    out=Path(outdir)
    out.mkdir(parents=True,exist_ok=True)
    captured=now or datetime.now(timezone.utc)
    if not isinstance(captured,datetime) or captured.tzinfo is None:
        raise ValueError("INVALID_CAPTURE_TIME")
    captured=captured.astimezone(timezone.utc)
    stamp=captured.isoformat()
    manifest={"schema":"football-king-raw-ft-source-candidates-v1",
              "captured_utc":stamp,"season_start":year,
              "status":"HOLD","independently_verified":False,
              "production_recommendations":"DISABLED","sources":[]}
    for provider,template in URLS.items():
        url=template.format(year=year,next_year=year+1,short_next_year=str(year+1)[-2:])
        item={"provider":provider,"source_url":url,"status":"ERROR"}
        try:
            body=getter(url)
            parsed=json.loads(body)
            if provider=="OpenLigaDB" and not isinstance(parsed,list):
                raise ValueError("UNEXPECTED_OPENLIGADB_SCHEMA")
            if provider=="OpenFootball" and (not isinstance(parsed,dict) or not isinstance(parsed.get("matches"),list)):
                raise ValueError("UNEXPECTED_OPENFOOTBALL_SCHEMA")
            digest=hashlib.sha256(body).hexdigest()
            name=provider.lower()+".json"
            (out/name).write_bytes(body)
            item.update(status="FETCHED_UNVERIFIED",raw_sha256=digest,raw_file=name,bytes=len(body))
        except (OSError,ValueError,TypeError,TimeoutError) as exc:
            item["error_type"]=type(exc).__name__
            if hasattr(exc,"code"):
                item["http_status"]=int(exc.code)
        manifest["sources"].append(item)
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--year",type=int,required=True)
    p.add_argument("--output-dir",required=True)
    a=p.parse_args()
    print(json.dumps(collect(a.year,a.output_dir),ensure_ascii=False))

if __name__=="__main__":
    main()
