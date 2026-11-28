"""Strict historical evidence intake. Never authorizes model/live consumption."""
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
from pathlib import Path

URLS={
    "football":{"https://api.openligadb.de/getmatchdata/bl1/2020/1",
                "https://raw.githubusercontent.com/openfootball/football.json/master/2020-21/de.1.json"},
    "quant":{"https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=2020-09-18&endPeriod=2020-09-18&format=csvdata",
             "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSEU&cosd=2020-09-18&coed=2020-09-18"}
}
EXPECTED={58577,58578,58579,58580,58581,58582,58584}
def bounded_rate(value):
    if not isinstance(value,str) or len(value)>64:
        raise ValueError("invalid numeric representation")
    rate=Decimal(value)
    if not rate.is_finite() or rate<=0 or len(rate.as_tuple().digits)>32 or abs(rate.as_tuple().exponent)>16:
        raise ValueError("rate precision or scale out of bounds")
    return rate

def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError("duplicate JSON key")
        result[key]=value
    return result

def read_evidence(path):
    with path.open("rb") as stream:
        raw=stream.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError("evidence too large")
    return json.loads(raw,object_pairs_hook=unique_object)

def intake(doc,domain,now):
    result={"schema":"scrapling-evidence-intake-v1","domain":domain,"status":"HOLD",
            "production_recommendations":"DISABLED","live_trading":"DISABLED",
            "model_input_allowed":False,"independent_upstream_certified":False,
            "evidence_metadata_accepted":False,"raw_body_verified":False}
    try:
        if now.tzinfo is None or doc["status"]!="HOLD" or doc["historical_only"] is not True or doc["production_recommendations"]!="DISABLED" or "error_type" in doc:
            raise ValueError("invalid safety state")
        # Input is derived metadata, not the raw upstream body. Never accept stronger claims.
        for flag in ("raw_body_verified","model_input_allowed","independent_upstream_certified"):
            if flag in doc and doc[flag] is not False:
                raise ValueError("unsupported evidence claim")
        if doc.get("live_trading","DISABLED")!="DISABLED":
            raise ValueError("unsafe live state")
        evidence=doc["source_evidence"]
        if not isinstance(evidence,list):raise ValueError("invalid evidence container")
        if len(evidence)!=2 or {x["url"] for x in evidence}!=URLS[domain]:
            raise ValueError("source identities")
        stamps=[]
        for x in evidence:
            if type(x["bytes"]) is not int or not 0<x["bytes"]<=2_000_000 or not re.fullmatch(r"[0-9a-f]{64}",x["sha256"]):
                raise ValueError("source metadata")
            t=datetime.fromisoformat(x["captured_utc"].replace("Z","+00:00"))
            if t.tzinfo is None or t>now:raise ValueError("capture time")
            stamps.append(t)
        if evidence[0]["sha256"]==evidence[1]["sha256"]:
            raise ValueError("duplicate body fingerprint")
        if abs((stamps[0]-stamps[1]).total_seconds())>120:
            raise ValueError("capture skew")
        if domain=="football":
            if doc["independent_upstream_certified"] is not False:raise ValueError("unproven independence")
            rows=doc["rows"]
            if not isinstance(rows,list) or any(type(r["match_id"]) is not int for r in rows) or len(rows)!=len(EXPECTED) or {r["match_id"] for r in rows}!=EXPECTED or doc["matched"]!=len(EXPECTED) or doc["expected"]!=len(EXPECTED):
                raise ValueError("coverage")
            for row in rows:
                a,b=row["score_a"],row["score_b"]
                if row["status"]!="HISTORICAL_MATCH" or not isinstance(a,list) or not isinstance(b,list) or len(a)!=2 or len(b)!=2 or any(type(v) is not int or v<0 for v in a+b) or a!=b:
                    raise ValueError("score conflict")
            result["historical_match_count"]=len(rows)
        elif domain=="quant":
            if doc["live_trading"]!="DISABLED" or doc["same_fixing_time"] is not False or doc["comparison"]!="DIFFERENT_FIXING_TIMES_RESEARCH_ONLY":
                raise ValueError("fixing semantics")
            a,b=bounded_rate(doc["ecb_usd_per_eur"]),bounded_rate(doc["fed_usd_per_eur"])
            if not all(v.is_finite() and v>0 for v in (a,b)):
                raise ValueError("invalid fx rate")
            delta=(abs(a-b)/a*10000).quantize(Decimal("0.01"))
            if delta!=Decimal(doc["relative_difference_bps"]):raise ValueError("difference mismatch")
            result["historical_difference_bps"]=str(delta)
        result["evidence_metadata_accepted"]=True
        result["report_sha256"]=hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
        result["reason"]="HISTORICAL_METADATA_ONLY_NOT_MODEL_INPUT"
    except (ValueError,TypeError,KeyError,AttributeError,DecimalException,OverflowError):
        result["evidence_metadata_accepted"]=False
        result.pop("report_sha256",None)
        result.pop("historical_match_count",None)
        result.pop("historical_difference_bps",None)
        result["reason"]="MISSING_OR_INVALID_EVIDENCE"
    return result

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("domain",choices=list(URLS));ap.add_argument("input",type=Path);ap.add_argument("output",type=Path)
    args=ap.parse_args()
    if args.input.resolve()==args.output.resolve():ap.error("input and output must differ")
    try:
        doc=read_evidence(args.input)
    except (OSError,ValueError,RecursionError):
        doc={}
    r=intake(doc,args.domain,datetime.now(timezone.utc))
    args.output.write_text(json.dumps(r,indent=2))
    if not r["evidence_metadata_accepted"]:raise SystemExit(2)
