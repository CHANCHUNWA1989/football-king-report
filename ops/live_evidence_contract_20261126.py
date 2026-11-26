"""Offline provenance contract; structural corroboration is not authenticated evidence."""
from collections.abc import Mapping
from ops.live_snapshot_market_audit_20261126 import aware

LIMIT = 60
CLOCK_SKEW = 2
PERIODS = {"FIRST_HALF": (0, 65), "SECOND_HALF": (45, 130)}

def _count_pair(x, maximum):
    return isinstance(x, (list, tuple)) and len(x)==2 and all(
        type(v) is int and 0<=v<=maximum for v in x)

def audit_evidence(rows, registry, fixture_id, as_of, *, previous=None):
    """Registry must be trusted configuration, never supplied by a feed.
    Registry entries: provider -> (upstream group, provider fixture ID).
    Result remains research-only even when all structural checks pass.
    """
    reasons=set()
    valid=[]
    try:
        now=aware(as_of)
    except (ValueError, TypeError, OverflowError):
        return _result({"INVALID_AS_OF"}, [])
    if not isinstance(rows,list) or not isinstance(registry,Mapping) or not isinstance(fixture_id,str) or not fixture_id.strip():
        return _result({"INVALID_INPUT"}, [])
    seen=set()
    for row in rows:
        if not isinstance(row,Mapping):
            reasons.add("INVALID_ROW")
            continue
        provider=row.get("provider")
        if not isinstance(provider,str) or provider not in registry:
            reasons.add("UNKNOWN_PROVIDER")
            continue
        config=registry[provider]
        if (not isinstance(config,(list,tuple)) or len(config)!=2 or
            any(not isinstance(v,str) or not v.strip() for v in config)):
            reasons.add("INVALID_REGISTRY")
            continue
        upstream,external_id=config
        if provider in seen:
            reasons.add("DUPLICATE_PROVIDER")
        seen.add(provider)
        if row.get("fixture_id")!=fixture_id or row.get("provider_fixture_id")!=external_id:
            reasons.add("FIXTURE_MISMATCH")
            continue
        try:
            event=aware(row.get("event_at"))
            observed=aware(row.get("observed_at"))
            if not event<=observed<=now or (now-event).total_seconds()>LIMIT:
                reasons.add("STALE_OR_FUTURE_EVIDENCE")
                continue
        except (ValueError,TypeError,OverflowError):
            reasons.add("INVALID_TIMESTAMP")
            continue
        period=row.get("period")
        minute=row.get("minute")
        if (not isinstance(period,str) or period not in PERIODS or type(minute) is not int
            or not PERIODS[period][0]<=minute<=PERIODS[period][1]):
            reasons.add("INVALID_CLOCK")
            continue
        score=row.get("score")
        reds=row.get("red_cards")
        if not _count_pair(score,30) or not _count_pair(reds,5):
            reasons.add("INVALID_SCORE_OR_RED_CARDS")
            continue
        if previous is not None:
            if (not isinstance(previous,Mapping) or not _count_pair(previous.get("score"),30)
                or not _count_pair(previous.get("red_cards"),5)
                or type(previous.get("minute")) is not int):
                reasons.add("INVALID_PREVIOUS_STATE")
            elif (minute<previous["minute"] or any(a<b for a,b in zip(score,previous["score"]))
                or any(a<b for a,b in zip(reds,previous["red_cards"]))):
                reasons.add("STATE_REGRESSION_REQUIRES_REVIEW")
        valid.append((upstream,period,minute,tuple(score),tuple(reds)))
    if len({v[0] for v in valid})<2:
        reasons.add("INDEPENDENT_UPSTREAMS_MISSING")
    if valid:
        if len({(v[1],v[3],v[4]) for v in valid})>1:
            reasons.add("STATE_CONFLICT")
        if max(v[2] for v in valid)-min(v[2] for v in valid)>CLOCK_SKEW:
            reasons.add("CLOCK_CONFLICT")
    return _result(reasons,valid)

def _result(reasons, valid):
    return {"structural_match":not reasons,"reasons":sorted(reasons),
            "valid_rows":len(valid),"distinct_upstreams":len({v[0] for v in valid}),
            "source_attestation_verified":False,"positive_ev_verified":False,
            "deployment":"HOLD","recommendations":"DISABLED","qualified":False}
