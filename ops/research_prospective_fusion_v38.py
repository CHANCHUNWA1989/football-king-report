"""Local prospective fusion receipt. No network or external timestamp witness.

The clock and source references are supplied by the caller and remain untrusted.
A receipt is not a signed prediction, authenticated source, or training admission.
"""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
from .research_candidate_gap_v6 import stamp,LEAGUES
from .research_live_intake_v4 import decode
from .research_missing_fixture_discovery_v16 import identity
from .research_attack_defence_replay_v35 import rates,vec
from .research_market_fusion_v37 import candidate,POLICY,normalized

REGISTRATION_NOT_BEFORE="2026-11-28T00:00:00Z"
MAX_HISTORY=2000
FIELDS=("research_prospective_fusion_v38.py","research_market_fusion_v37.py",
        "research_attack_defence_replay_v35.py","research_multimodel_v1.py",
        "research_candidate_gap_v6.py","research_live_intake_v4.py",
        "research_missing_fixture_discovery_v16.py","team_identity.py")
def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

def manifest():
    root=Path(__file__).resolve().parent
    files={}
    for name in FIELDS:
        p=root/name
        if p.is_symlink() or not p.is_file():raise ValueError("unsafe local source")
        with p.open("rb") as f:raw=f.read(2_000_001)
        if not 0<len(raw)<=2_000_000:raise ValueError("source size")
        files[name]=sha(raw)
    return {"files":files,"python_implementation":platform.python_implementation(),
            "python_version":list(sys.version_info[:3])}

def exact(obj,keys):
    if not isinstance(obj,dict) or set(obj)!=set(keys.split()):
        raise ValueError("unexpected input fields")

def token(value,limit=160):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,"+str(limit-1)+r"}",value):
        raise ValueError("invalid identifier")
    return value

def fingerprint(value):
    if not isinstance(value,str) or not re.fullmatch("[0-9a-f]{64}",value):
        raise ValueError("invalid evidence digest")
    return value

def fixture(row):
    league=row["league"]
    if league not in LEAGUES:raise ValueError("unsupported league")
    for field in ("home","away"):
        s=row[field]
        if not isinstance(s,str) or not 0<len(s)<=100 or not s.strip():
            raise ValueError("invalid team")
    return identity(league,row["home"],row["away"],row["kickoff_utc"])

def capture(raw,*,as_of):
    before=manifest();doc=decode(raw)
    exact(doc,"schema event_id league home away kickoff_utc forecast_utc market history")
    if doc["schema"]!="prospective-fusion-input-v38":raise ValueError("input schema")
    event=token(doc["event_id"]);key=fixture(doc)
    f=stamp(doc["forecast_utc"]);now=stamp(as_of)
    if not stamp(REGISTRATION_NOT_BEFORE)<=f<=now<=f+timedelta(seconds=60) or now>key[3]-timedelta(minutes=10):
        raise ValueError("forecast clock or registration window")
    m=doc["market"];exact(m,"captured_utc p source_id evidence_sha256")
    token(m["source_id"]);fingerprint(m["evidence_sha256"])
    mt=stamp(m["captured_utc"]);market=normalized(m["p"])
    if mt>f:raise ValueError("future market")
    history=doc["history"]
    if not isinstance(history,list) or len(history)>MAX_HISTORY:raise ValueError("history size")
    pool=[];seen=set();seen_ids=set();teams_at=set()
    for r in history:
        exact(r,"league home away kickoff_utc observed_utc score source_id fixture_id evidence_sha256")
        k=fixture(r);t=stamp(r["observed_utc"]);s=r["score"]
        source_id=token(r["source_id"]);fid=token(r["fixture_id"])
        fingerprint(r["evidence_sha256"])
        if (k==key or k in seen or (source_id,fid) in seen_ids
            or any((k[0],team,k[3]) in teams_at for team in k[1:3])
            or not k[3]+timedelta(minutes=90)<=t or not t+timedelta(hours=24)<f
            or not isinstance(s,list) or len(s)!=2 or any(type(x) is not int or not 0<=x<=30 for x in s)):
            raise ValueError("invalid or future history")
        seen.add(k);seen_ids.add((source_id,fid))
        teams_at.update((k[0],team,k[3]) for team in k[1:3])
        pool.append((t,k,tuple(s)))
    pool.sort()
    h,a,support=rates(pool,key);model=vec(h,a)
    result=candidate(model,market,support=support,market_age_seconds=(f-mt).total_seconds())
    if manifest()!=before:raise ValueError("local source changed")
    receipt={"schema":"prospective-fusion-local-receipt-v38","policy":POLICY,
             "registration_not_before":REGISTRATION_NOT_BEFORE,"event_id":event,
             "fixture":[*key[:3],key[3].isoformat()],"forecast_utc":f.isoformat(),
             "receipt_clock_utc":now.isoformat(),"raw_input_sha256":sha(raw),
             "source_manifest":before,"support":list(support),"model_p":model,
             "market_p":market,"candidate":result,
             "external_time_witness_verified":False,"source_authenticity_verified":False,
             "cohort_completeness_proven":False,"authenticated_samples":0,
             "training_admission":False,"model_promotion_allowed":False,
             "production_recommendations":"DISABLED","status":"HOLD"}
    receipt["receipt_sha256"]=sha(canonical(receipt))
    return receipt

def replay(receipt,raw):
    """Exact regeneration with original bytes and locally matching source files."""
    expected=capture(raw,as_of=receipt["receipt_clock_utc"])
    if canonical(expected)!=canonical(receipt):raise ValueError("receipt mismatch")
    return expected
