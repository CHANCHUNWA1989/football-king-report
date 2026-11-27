"""Read-only capability audit from existing source reports; no new network calls."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from .research_live_intake_v4 import decode, MAX_BYTES
from .research_unified_live_v2 import utc, digest

REPORTS={
    "extra":("sources/latest.json","football-king-extra-source-audit-v1","collected_utc"),
    "germany":("sources/live_germany_latest.json","football-king-openligadb-hourly-v1","collected_utc"),
    "market":("sources/six_league_free_latest.json","football-king-six-free-league-quality-v1","captured_utc"),
    "bsd":("sources/bsd_status_latest.json","football-king-bsd-free-research-v1","captured_utc"),
    "hkjc":("sources/hkjc_tipsme_free_latest.json","football-king-hkjc-tipsme-free-research-v1","captured_utc"),
    "extensions":("sources/research_extensions_latest.json","football-king-free-research-extensions-v1","completed_utc"),
}
EXPECTED={
    "extra":("thesportsdb","api_football","football_data_org","sportmonks"),
    "extensions":("openfootapi","statsbomb_open_data"),
}
# Snapshot age is only an availability diagnostic, never live tick freshness.
MAX_REPORT_AGE=86400

def audit(documents, *, as_of):
    now=utc(as_of)
    out={"schema":"live-source-capability-v9","checked_utc":now.isoformat(),
         "status":"HOLD","production_recommendations":"DISABLED",
         "live_training_eligible":False,"source_authenticity_verified":False,
         "live_score_origins_verified":0,"live_xg_origins_verified":0,
         "executable_live_quotes_verified":0,"new_network_calls":0,
         "reports":{},"providers":{}}
    for name,(_,schema,clock) in REPORTS.items():
        d=documents.get(name)
        try:
            if not isinstance(d,dict) or d.get("schema")!=schema or d.get("production_recommendations")!="DISABLED":
                raise ValueError("wrong schema or status")
            t=utc(d[clock]); age=(now-t).total_seconds()
            if not 0<=age<=MAX_REPORT_AGE:
                raise ValueError("stale or future report")
            if name in EXPECTED:
                providers=d["providers"]
                ids=[p["provider"] for p in providers]
                if len(ids)!=len(set(ids)) or set(ids)!=set(EXPECTED[name]):
                    raise ValueError("wrong provider roster")
                items=[(p["provider"],p) for p in providers]
            else:
                key={"germany":"openligadb","market":"propline","bsd":"bzzoiro_sports_data",
                     "hkjc":"tipsme_hkjc_third_party"}[name]
                if name=="germany":
                    if d.get("source")!="OpenLigaDB":raise ValueError("wrong source")
                elif d.get("provider")!=key:raise ValueError("wrong source")
                items=[(key,d)]
            # Never interpret provider status as a verified live capability.
            entries={}
            for key,p in items:
                status=p["status"]
                if not isinstance(status,str) or not status or len(status)>100:
                    raise ValueError("bad status")
                flags=p.get("warnings",p.get("issues",[]))
                if not isinstance(flags,list) or len(flags)>50 or any(not isinstance(x,str) or len(x)>200 for x in flags):
                    raise ValueError("invalid blockers")
                entries[key]={"reported_status":status,"reported_blockers":flags,
                              "report":name,"verified_live_capability":False}
            out["reports"][name]={"state":"FRESH_REPORT_ONLY","as_of":t.isoformat(),"sha256":digest(d)}
            out["providers"].update(entries)
        except (KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError):
            out["reports"][name]={"state":"MISSING_STALE_OR_INVALID"}
    out["blockers"]=["TWO_AUTHENTICATED_LIVE_SCORE_ORIGINS_MISSING",
                     "TWO_AUTHENTICATED_RECENT_NPXG_ORIGINS_MISSING",
                     "EXTERNAL_FORECAST_WITNESS_MISSING"]
    out["market_blockers"]=["EXECUTABLE_LIVE_ASIAN_QUOTE_UNVERIFIED"]
    out["note"]="Availability reports are not live capture envelopes; historical data and consensus prices never substitute."
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    a=p.parse_args()
    docs={}
    for key,(rel,_,_) in REPORTS.items():
        try:
            with (a.root/rel).open("rb") as stream: docs[key]=decode(stream.read(MAX_BYTES+1))
        except (OSError,ValueError,TypeError,RecursionError):pass
    print(json.dumps(audit(docs,as_of=datetime.now(timezone.utc).isoformat()),sort_keys=True,allow_nan=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
