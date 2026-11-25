"""Read-only monitor of cached collector metadata, not a live prediction service."""
from datetime import datetime, timezone
import json
from pathlib import Path
from vnext_live_auto_audit import _unique

SOURCES = {
    "hkjc_third_party": ("sources/hkjc_tipsme_free_latest.json",
        "football-king-hkjc-tipsme-free-research-v1", "captured_utc", 26*3600),
    "german_community": ("sources/live_germany_latest.json",
        "football-king-openligadb-hourly-v1", "collected_utc", 2*3600),
    "wide_fixtures": ("sources/wide_latest.json", None, "collected_utc", 26*3600),
}
MAX_BYTES = 2_000_000

def inspect(doc, schema, stamp, limit, now):
    if type(doc) is not dict or doc.get("production_recommendations") != "DISABLED":
        return "INVALID_METADATA"
    if schema is not None and doc.get("schema") != schema:
        return "INVALID_METADATA"
    try:
        observed = datetime.fromisoformat(doc[stamp].replace("Z","+00:00"))
        if observed.tzinfo is None or now.tzinfo is None:
            return "INVALID_CLOCK"
        age=(now-observed).total_seconds()
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return "INVALID_CLOCK"
    if age<0:
        return "FUTURE_METADATA"
    if doc.get("status")=="NOT_CONFIGURED":
        return "NOT_CONFIGURED"
    if age>limit:
        return "STALE_METADATA"
    if doc.get("status")=="RESEARCH_ONLY":
        return "RECENT_RESEARCH_METADATA_ONLY"
    if doc.get("status")=="HOLD":
        return "SOURCE_HOLD"
    return "INVALID_METADATA"

def monitor(root, now):
    result={}
    for key,(path,schema,stamp,limit) in SOURCES.items():
        try:
            with (root / path).open("rb") as f:
                raw=f.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:
                raise ValueError("OVERSIZE")
            doc=json.loads(raw.decode("utf-8"),object_pairs_hook=_unique)
            result[key]=inspect(doc,schema,stamp,limit,now)
        except FileNotFoundError:
            result[key]="MISSING_METADATA"
        except (OSError,ValueError,TypeError,RecursionError):
            result[key]="INVALID_METADATA"
    return {"schema":"football-king-live-auto-monitor-v1",
            "checked_utc":now.isoformat(),"status":"HOLD",
            "source_metadata_status":result,"provider_calls":0,
            "actual_live_score_verified":False,"actual_xg_verified":False,
            "actual_live_odds_verified":False,"positive_ev_verified":False,
            "production_recommendations":"DISABLED"}

if __name__=="__main__":
    print(json.dumps(monitor(Path(__file__).resolve().parents[1],
                             datetime.now(timezone.utc)),sort_keys=True))
