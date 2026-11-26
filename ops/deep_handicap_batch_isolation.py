"""Batch DHE replay isolation and collision checks, offline private research.

Inputs are claimed evidence, never authenticated. Reject every record involved
in a collision, including a structurally invalid record that reuses an identity.
No source fetching, promotion, odds, or model weight changes.
"""
from collections import Counter, defaultdict
from live_score_identity_guard import parse_utc
from deep_handicap_replay_bridge import bridge, _hash

SCHEMA="football-king-dhe-batch-isolation-v1"
MAX_BATCH=1000


def _text(v):
    return type(v) is str and 0<len(v)<=160 and v==v.strip()


def _claims(item):
    """Extract collision keys even from records later rejected by the bridge."""
    keys=set()
    if type(item) is not dict:
        return keys
    r=item.get("capture_report")
    c=r.get("candidate") if type(r) is dict else None
    if type(c) is dict:
        l,f,h,a=(c.get(k) for k in ("league_id","fixture_id","home_id","away_id"))
        if _text(l) and _text(f):
            keys.add(("fixture",l,f))
        if all(_text(x) for x in (l,h,a)):
            try:
                ko=parse_utc(c.get("kickoff_utc")).isoformat()
                keys.add(("teams_kickoff",l,*sorted((h,a)),ko))
            except (ValueError,TypeError,OverflowError):
                pass
        e=c.get("evidence")
        if type(e) is dict:
            if _text(e.get("market_event_id")):
                keys.add(("market_event",e["market_event_id"]))
            for name in ("shadow_projection_sha256","private_quote_report_sha256"):
                if _hash(e.get(name)):
                    keys.add((name,e[name]))
    for v in (item.get("expected_candidate_sha256"),
              r.get("candidate_sha256") if type(r) is dict else None):
        if _hash(v):
            keys.add(("candidate_digest",v))
    m=item.get("mapping")
    if type(m) is dict and type(m.get("provider_event_ids")) is dict:
        for provider,ev in m["provider_event_ids"].items():
            if _text(provider) and _text(ev):
                keys.add(("provider_event",provider,ev))
    obs=item.get("observations")
    if type(obs) is list and len(obs)<=10:
        for o in obs:
            if type(o) is not dict:
                continue
            p,e=o.get("provider"),o.get("source_event_id")
            if _text(p) and _text(e):
                keys.add(("provider_event",p,e))
            if _hash(o.get("evidence_sha256")):
                keys.add(("result_digest",o["evidence_sha256"]))
    return keys


def isolate(items,*,as_of_utc):
    """All-or-none collision rejection; no scoring of authenticated cases.

    Collisions use claims from all records, not just those passing the bridge.
    This conservative policy can exclude valid records on malformed input.
    A distinct ID or hash is not proof of distinct real-world evidence.
    """
    out={"schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
         "research_only":True,"private_output_only":True,
         "source_authenticated":False,"true_forward_sample_count":0,
         "qualifies_for_betting":False,"positive_expected_value_verified":False,
         "evaluation_rows":[],"rejections":{},"collision_types":{}}
    if type(items) is not list or len(items)>MAX_BATCH:
        return {**out,"reason":"INVALID_BATCH"}
    try:
        parse_utc(as_of_utc)
    except (ValueError,TypeError,OverflowError):
        return {**out,"reason":"INVALID_CLOCK"}
    owners=defaultdict(set)
    for i,item in enumerate(items):
        for k in _claims(item):
            owners[k].add(i)
    collision=defaultdict(set)
    for key,indices in owners.items():
        if len(indices)>1:
            for i in indices:
                collision[i].add(key[0])
    rejects=Counter()
    types=Counter()
    accepted=[]
    for i,item in enumerate(items):
        if i in collision:
            rejects["BATCH_COLLISION"]+=1
            types.update(collision[i])
            continue
        if type(item) is not dict or set(item)!={"capture_report","mapping","observations",
                "expected_candidate_sha256","data_kind"}:
            rejects["INVALID_BATCH_ITEM"]+=1
            continue
        result=bridge(item["capture_report"],item["mapping"],item["observations"],
                      expected_candidate_sha256=item["expected_candidate_sha256"],
                      as_of_utc=as_of_utc,data_kind=item["data_kind"])
        row=result.get("evaluation_row")
        if row is None:
            rejects["BRIDGE_REJECTED"]+=1
            continue
        accepted.append(row)
    out.update(reason="STRUCTURAL_BATCH_ONLY",input_count=len(items),
               evaluation_rows=accepted,accepted_count=len(accepted),
               rejections=dict(sorted(rejects.items())),collision_types=dict(sorted(types.items())),
               cohort_counts={k:sum(r["data_kind"]==k for r in accepted)
                              for k in ("SYNTHETIC","EXTERNAL_UNAUTHENTICATED")})
    return out
