"""One-shot source health audit, not a live feed or a trading decision."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from evidence_intake import URLS, intake, read_evidence

MAX_CAPTURE_AGE=300

def assess(domain, doc, now):
    result={"domain":domain,"status":"HOLD","live_trading":"DISABLED",
            "production_recommendations":"DISABLED","model_input_allowed":False,
            "automatic_failover_allowed":False,"historical_only":True,
            "independent_upstream_certified":False,"sources":[]}
    checked=intake(doc,domain,now)
    rows=doc.get("source_evidence",[]) if isinstance(doc,dict) else []
    if not isinstance(rows,list):rows=[]
    for url in sorted(URLS[domain]):
        state="MISSING_OR_INVALID"
        age=None
        matches=[x for x in rows if isinstance(x,dict) and x.get("url")==url]
        if len(matches)==1:
            try:
                x=matches[0]
                stamp=datetime.fromisoformat(x["captured_utc"].replace("Z","+00:00"))
                if stamp.tzinfo is None or now.tzinfo is None:raise ValueError("naive time")
                age=(now-stamp).total_seconds()
                if age<0:state="FUTURE_CAPTURE"
                elif age>MAX_CAPTURE_AGE:state="STALE_CAPTURE"
                elif checked["evidence_metadata_accepted"]:state="RECENT_HISTORICAL_METADATA"
                else:state="UNVERIFIED_CAPTURE"
            except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
                pass
        elif len(matches)>1:state="DUPLICATE_SOURCE"
        result["sources"].append({"url":url,"state":state,"capture_age_seconds":age})
    result["evidence_metadata_accepted"]=checked["evidence_metadata_accepted"]
    result["health"]="HISTORICAL_METADATA_OK" if all(x["state"]=="RECENT_HISTORICAL_METADATA" for x in result["sources"]) else "DEGRADED_HOLD"
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("domain",choices=list(URLS))
    p.add_argument("input",type=Path)
    p.add_argument("output",type=Path)
    a=p.parse_args()
    if a.input.resolve()==a.output.resolve():p.error("input and output must differ")
    try:doc=read_evidence(a.input)
    except (OSError,ValueError,RecursionError):doc={}
    r=assess(a.domain,doc,datetime.now(timezone.utc))
    a.output.write_text(json.dumps(r,indent=2),encoding="utf-8")
    return 0 if r["health"]=="HISTORICAL_METADATA_OK" else 2

if __name__=="__main__":raise SystemExit(main())
