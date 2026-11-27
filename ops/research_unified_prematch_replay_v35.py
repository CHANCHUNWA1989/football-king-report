"""V35: deterministic local replay of V34 prematch evidence.
A self-hash is integrity metadata, NOT independent evidence or a timestamp witness.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
from .research_unified_prematch_audit_v34 import Forecast, audit
from .research_market_provenance_v1 import Quote
from .research_model_source_binding_v1 import model_source_manifest

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)

def digest(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()

def clock(t):
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("timezone required")
    return t.astimezone(timezone.utc).isoformat()

def manifest(root):
    base=Path(root).resolve()
    files=dict(model_source_manifest(root=base)["files"])
    for name in ("research_model_source_binding_v1","research_unified_prematch_audit_v34",
                 "research_unified_prematch_replay_v35"):
        relative="ops/"+name+".py"
        path=(base/relative).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise ValueError("missing or unsafe source")
        files[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    return files

def freeze(*,event_id,kickoff,now,forecasts,quotes,handicap_line,totals_line,
           delta=0.15,root="."):
    if not 2<=len(forecasts)<=8 or not 1<=len(quotes)<=128:
        raise ValueError("invalid evidence count")
    fs=[dict(asdict(f),kickoff=clock(f.kickoff),observed=clock(f.observed)) for f in forecasts]
    qs=[dict(asdict(q),observed_at=clock(q.observed_at),kickoff_at=clock(q.kickoff_at)) for q in quotes]
    fs=sorted(fs,key=canonical)
    qs=sorted(qs,key=canonical)
    payload={"schema":"unified-prematch-replay-v35","event_id":event_id,
             "kickoff":clock(kickoff),"frozen_at":clock(now),"forecasts":fs,"quotes":qs,
             "handicap_line":handicap_line,"totals_line":totals_line,"delta":delta,
             "source_manifest":manifest(root),"status":"HOLD",
             "production_recommendations":"DISABLED","external_timestamp_verified":False,
             "source_identity_authenticated":False,"training_admission":False,
             "qualified_for_production":False}
    payload["audit"]=replay_audit(payload)
    if payload["audit"].get("audit_completed") is not True:
        raise ValueError("V34 audit rejected inputs: "+str(payload["audit"].get("reason")))
    payload["sha256"]=digest(payload)
    return payload

def replay_audit(p):
    parse=datetime.fromisoformat
    fs=[Forecast(**dict(f,kickoff=parse(f["kickoff"]),observed=parse(f["observed"]))) for f in p["forecasts"]]
    qs=[Quote(**dict(q,observed_at=parse(q["observed_at"]),kickoff_at=parse(q["kickoff_at"]))) for q in p["quotes"]]
    return audit(event_id=p["event_id"],kickoff=parse(p["kickoff"]),now=parse(p["frozen_at"]),
                 forecasts=fs,quotes=qs,handicap_line=p["handicap_line"],
                 totals_line=p["totals_line"],delta=p["delta"])

def verify(record,*,root="."):
    result={"status":"HOLD","production_recommendations":"DISABLED",
            "replay_verified":False,"external_timestamp_verified":False,
            "source_identity_authenticated":False,"training_admission":False,
            "qualified_for_production":False}
    try:
        if not isinstance(record,dict) or not 2<=len(record["forecasts"])<=8 or not 1<=len(record["quotes"])<=128:
            raise ValueError("invalid record")
        body={k:v for k,v in record.items() if k!="sha256"}
        if record["sha256"]!=digest(body):
            raise ValueError("digest mismatch")
        if record["source_manifest"]!=manifest(root):
            raise ValueError("model source mismatch")
        parse=datetime.fromisoformat
        fs=[Forecast(**dict(f,kickoff=parse(f["kickoff"]),observed=parse(f["observed"]))) for f in record["forecasts"]]
        qs=[Quote(**dict(q,observed_at=parse(q["observed_at"]),kickoff_at=parse(q["kickoff_at"]))) for q in record["quotes"]]
        expected=freeze(event_id=record["event_id"],kickoff=parse(record["kickoff"]),
                        now=parse(record["frozen_at"]),forecasts=fs,quotes=qs,
                        handicap_line=record["handicap_line"],totals_line=record["totals_line"],
                        delta=record["delta"],root=root)
        if canonical(expected)!=canonical(record):
            raise ValueError("canonical replay mismatch")
        result["replay_verified"]=True
    except (ValueError,TypeError,KeyError,AttributeError,OSError,OverflowError) as exc:
        result["reason"]=str(exc)
    return result
