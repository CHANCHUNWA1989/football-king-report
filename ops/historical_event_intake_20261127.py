"""Offline intake for normalized, locally licensed historical event files.
No downloads, no data redistribution, no production or betting use.
Availability timestamps must be independently attested before prospective use.
"""
from collections.abc import Mapping
from hashlib import sha256
from json import loads
from math import fsum
from ops.live_snapshot_market_audit_20261126 import aware
from ops.live_score_challenger_20261127 import number

MAX_BYTES=20_000_000

def _id(v):
    if not isinstance(v,str) or not v or v.strip()!=v:
        raise ValueError("invalid identity")
    return v

def intake(raw, *, expected_sha256, fixture_id, cutoff_seconds, source_id):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:
        raise ValueError("invalid input size")
    digest=sha256(raw).hexdigest()
    if digest!=expected_sha256:
        raise ValueError("archive digest mismatch")
    _id(fixture_id); _id(source_id)
    if type(cutoff_seconds) is not int or not 0<=cutoff_seconds<=7200:
        raise ValueError("invalid cutoff")
    payload=loads(raw)
    if not isinstance(payload,Mapping) or payload.get("fixture_id")!=fixture_id or payload.get("source_id")!=source_id:
        raise ValueError("fixture or source mismatch")
    events=payload.get("events")
    if not isinstance(events,list):
        raise ValueError("missing event list")
    ids=set()
    last=(-1,-1)
    sums={"home":[],"away":[]}
    shots={"home":0,"away":0}
    reds={"home":0,"away":0}
    included=0
    for e in events:
        if not isinstance(e,Mapping):
            raise ValueError("invalid event")
        eid=_id(e.get("event_id"))
        if eid in ids:
            raise ValueError("duplicate event")
        ids.add(eid)
        sec=e.get("elapsed_play_seconds")
        seq=e.get("sequence")
        if type(sec) is not int or not 0<=sec<=7200 or type(seq) is not int or seq<0:
            raise ValueError("invalid chronology")
        key=(sec,seq)
        if key<=last:
            raise ValueError("nonmonotone event order")
        last=key
        kind=e.get("kind")
        team=e.get("side")
        if kind not in ("SHOT","ON_FIELD_DISMISSAL","OTHER") or team not in ("home","away"):
            raise ValueError("unsupported event semantics")
        if kind=="SHOT":
            x=e.get("shot_xg")
            if not number(x) or not 0<=x<=1:
                raise ValueError("missing or invalid shot xG")
        if sec>=cutoff_seconds:
            continue
        included+=1
        if kind=="SHOT":
            shots[team]+=1
            sums[team].append(x)
        elif kind=="ON_FIELD_DISMISSAL":
            reds[team]+=1
            if reds[team]>4:
                raise ValueError("abandoned or unsupported match state")
    return {"fixture_id":fixture_id,"source_id":source_id,"archive_sha256":digest,
            "cutoff_seconds_exclusive":cutoff_seconds,"events_before_cutoff":included,
            "shot_counts":shots,"historical_cumulative_shot_xg":{k:fsum(v) for k,v in sums.items()},
            "on_field_dismissals":reds,"availability_attested":False,
            "source_attestation_verified":False,"license_verified":False,
            "live_xg_verified":False,"out_of_sample_verified":False,
            "deployment":"HOLD","recommendations":"DISABLED","qualified":False}
