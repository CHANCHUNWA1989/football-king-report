"""Offline live capture intake. Does not authenticate provider identity or collect feeds."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .research_live_evidence_v3 import seal
from .research_unified_live_v2 import digest, utc, text

MAX_BYTES=2_000_000
KINDS=("score","stats","quote","prior")

def unique(items):
    out={}
    for k,v in items:
        if k in out:
            raise ValueError("duplicate JSON key")
        out[k]=v
    return out

def bad_constant(value):
    raise ValueError("nonfinite JSON")

def decode(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:
        raise ValueError("capture size")
    obj=json.loads(raw.decode("utf-8"),object_pairs_hook=unique,parse_constant=bad_constant)
    if not isinstance(obj,dict):
        raise ValueError("object required")
    return obj

def intake(raw_captures, policy, *, event_id, as_of, model_release):
    """Policy is a local operator mapping, not independent source attestation.
    Only canonical adapter envelopes are accepted, never arbitrary provider schemas.
    """
    now=utc(as_of)
    result={"status":"HOLD","production":"DISABLED","source_authenticity_verified":False,
            "external_anchor_verified":False,"eligible_for_training":False,"reasons":[]}
    try:
        text(event_id); text(model_release)
        if not isinstance(raw_captures,list) or len(raw_captures)!=6:
            raise ValueError("six capture envelopes required")
        if policy["schema"]!="live-intake-policy-v1":
            raise ValueError("unsupported policy")
        fixture=policy["fixtures"][event_id]
        kickoff=utc(fixture["kickoff"])
        material=utc(fixture["last_material_event"])
        if not kickoff<=material<=now:
            raise ValueError("invalid material event")
        buckets={k:[] for k in KINDS}; bindings=[]
        seen=set()
        for raw in raw_captures:
            envelope=decode(raw)
            if envelope["schema"]!="live-adapter-envelope-v1":
                raise ValueError("unsupported envelope")
            adapter=text(envelope["adapter"])
            kind=envelope["kind"]
            if kind not in KINDS or (kind,adapter) in seen:
                raise ValueError("duplicate or invalid adapter")
            seen.add((kind,adapter))
            spec=policy["adapters"][adapter]
            if kind not in spec["kinds"]:
                raise ValueError("adapter kind not allowed")
            origin=text(spec["origin"])
            source=text(spec["source"])
            if envelope["provider_fixture_id"]!=fixture["provider_ids"][adapter]:
                raise ValueError("provider fixture mismatch")
            capture=utc(envelope["captured_at"])
            if capture>now:
                raise ValueError("future capture")
            payload=envelope["payload"]
            if not isinstance(payload,dict):
                raise ValueError("invalid payload")
            # Provider-origin identifiers come from policy, never from payload.
            if set(payload)&{"event_id","origin","source","captured","frozen_at"}:
                raise ValueError("reserved payload field")
            if kind=="prior":
                if capture>=kickoff or not utc(payload["updated"])<=capture:
                    raise ValueError("prior not frozen before kickoff")
                if set(payload)!={"home_xg","away_xg","updated"}:
                    raise ValueError("invalid prior payload")
                normalized={"event_id":event_id,"home_xg":payload["home_xg"],
                            "away_xg":payload["away_xg"],"frozen_at":capture.isoformat()}
            else:
                if not material<=utc(payload["updated"])<=capture:
                    raise ValueError("invalid capture order")
                normalized={**payload,"event_id":event_id,"source":source,"origin":origin,
                            "captured":capture.isoformat()}
            buckets[kind].append(normalized)
            bindings.append({"adapter":adapter,"kind":kind,"origin":origin,"source":source,
                             "raw_sha256":hashlib.sha256(raw).hexdigest(),
                             "normalized_sha256":digest(normalized)})
        if [len(buckets[k]) for k in KINDS]!=[2,2,1,1]:
            raise ValueError("capture coverage incomplete")
        snapshot={"event_id":event_id,"kickoff":kickoff.isoformat(),
                  "last_material_event":material.isoformat(),"score":buckets["score"],
                  "stats":buckets["stats"],"quote":buckets["quote"][0]}
        bundle=seal(snapshot,buckets["prior"][0],as_of=now.isoformat(),
                    captured_at=now.isoformat(),model_release=model_release)
        result.update(bundle=bundle,capture_bindings=bindings,policy_sha256=digest(policy),
                      structural_intake_passed=True,
                      reasons=["UNAUTHENTICATED_CAPTURE","UNVERIFIED_PROVIDER_INDEPENDENCE","NO_EXTERNAL_ANCHOR"])
    except (KeyError,TypeError,ValueError,OverflowError,AttributeError,RecursionError):
        result.update(structural_intake_passed=False,reasons=["INVALID_OR_INCOMPLETE_CAPTURE"])
    return result

def main():
    p=argparse.ArgumentParser(description="Offline canonical capture research intake")
    p.add_argument("--policy",type=Path,required=True)
    p.add_argument("--event",required=True)
    p.add_argument("--release",required=True)
    p.add_argument("--capture",type=Path,nargs=6,required=True)
    a=p.parse_args()
    def read(path):
        with path.open("rb") as stream:
            return stream.read(MAX_BYTES+1)
    try:
        report=intake([read(f) for f in a.capture],decode(read(a.policy)),
                      event_id=a.event,as_of=datetime.now(timezone.utc).isoformat(),model_release=a.release)
    except (OSError,ValueError,TypeError):
        report={"status":"HOLD","production":"DISABLED","structural_intake_passed":False}
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0 if report.get("structural_intake_passed") else 2

if __name__=="__main__":
    raise SystemExit(main())
