"""Read-only adapter for existing sanitized 1X2 market archives.

No new provider calls, quota consumption, live quotes or source authentication.
A market component is not a complete prospective input or an executable price.
"""
from collections import Counter
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from .market_archive_guard import check
from .research_live_intake_v4 import decode,MAX_BYTES
from .research_candidate_gap_v6 import stamp,LEAGUES
from .research_prospective_fusion_v38 import sha,token,REGISTRATION_NOT_BEFORE
from .research_missing_fixture_discovery_v16 import identity
from .research_market_fusion_v37 import normalized,MAX_AGE_SECONDS

MIN_LEAD_MINUTES=15
SOURCE_ID="the-odds-api.com:v4"

def audit(raw,*,as_of,include_components=False):
    if type(include_components) is not bool:raise ValueError("invalid component mode")
    now=stamp(as_of)
    d=decode(raw);captured=check(d)
    if captured>now:raise ValueError("future snapshot")
    if d["status"]=="RESEARCH_ONLY" and (
        d.get("market")!="h2h" or d.get("requested_markets")!=["h2h"]
        or d.get("raw_bookmaker_names_redistributed") is not False
        or d.get("market_probabilities_calibrated") is not False
        or d.get("model_value_advantage_verified") is not False):
        raise ValueError("unsafe market scope")
    digest=sha(raw);states=Counter();components=[]
    seen=set();ids=set()
    for r in d["events"]:
        if r["league"] not in LEAGUES:raise ValueError("unsupported league")
        k=identity(r["league"],r["home"],r["away"],r["kickoff_utc"])
        sid=token(r["source_event_id"])
        if k in seen or sid in ids:raise ValueError("ambiguous market identity")
        seen.add(k);ids.add(sid)
        updated=stamp(r["market_last_update_utc"])
        if updated>captured:raise ValueError("future market update")
        p=normalized([r["p_home"],r["p_draw"],r["p_away"]])
        if d["status"]!="RESEARCH_ONLY":
            state="SOURCE_HOLD"
        elif now-captured>timedelta(seconds=MAX_AGE_SECONDS):
            state="STALE_SNAPSHOT"
        elif now-updated>timedelta(seconds=MAX_AGE_SECONDS):
            state="STALE_OLDEST_UPDATE"
        elif k[3]<now+timedelta(minutes=MIN_LEAD_MINUTES):
            state="INSUFFICIENT_KICKOFF_LEAD"
        elif now<stamp(REGISTRATION_NOT_BEFORE):
            state="BEFORE_REGISTRATION_WINDOW"
        else:
            state="MARKET_COMPONENT_CANDIDATE"
            # V38 calls this field captured_utc. Use the oldest constituent
            # update conservatively for its freshness calculation, not the
            # later archive capture. Preserve both actual recorded clocks.
            components.append({"event_id":sid,"league":r["league"],
                "home":r["home"],"away":r["away"],"kickoff_utc":k[3].isoformat(),
                "snapshot_captured_utc":captured.isoformat(),
                "oldest_market_update_utc":updated.isoformat(),
                "market":{"captured_utc":updated.isoformat(),"p":p,
                          "source_id":SOURCE_ID,"evidence_sha256":digest}})
        states[state]+=1
    report={"schema":"prospective-market-readiness-v41","status":"HOLD",
            "snapshot_sha256":digest,"snapshot_captured_utc":captured.isoformat(),
            "snapshot_age_seconds":(now-captured).total_seconds(),
            "audit_clock_utc":now.isoformat(),"snapshot_events":len(d["events"]),
            "states":dict(states),"market_components":len(components),
            "minimum_lead_minutes":MIN_LEAD_MINUTES,"maximum_market_age_seconds":MAX_AGE_SECONDS,
            "provider_calls_made":0,"source_authenticity_verified":False,
            "complete_prospective_inputs":0,"external_witnesses_created":0,
            "market_prices_executable":False,"authenticated_samples":0,
            "training_admission":False,"model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
    if include_components:report["components"]=components
    return report

def from_root(root,*,as_of,include_components=False):
    path=root/"market/latest.json"
    if any(p.is_symlink() for p in (root,root/"market",path)) or not path.is_file():
        raise ValueError("unsafe market file")
    with path.open("rb") as f:raw=f.read(MAX_BYTES+1)
    return audit(raw,as_of=as_of,include_components=include_components)

def main():
    try:
        r=from_root(Path("."),as_of=datetime.now(timezone.utc).isoformat())
        print(json.dumps(r,sort_keys=True,allow_nan=False))
    except (OSError,ValueError,KeyError,TypeError,AttributeError,OverflowError,RecursionError):
        print(json.dumps({"status":"HOLD","reason":"INVALID_MARKET_SNAPSHOT","production_recommendations":"DISABLED"}))
        return 1
    return 0
if __name__=="__main__":
    raise SystemExit(main())
