"""Deterministic live score freshness comparator. Never infer freshness from score."""
from datetime import datetime, timezone

def _parse(value):
    if not isinstance(value,str) or not value.strip():
        return None
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)

def audit_snapshots(snapshots, *, fixture_id):
    if not isinstance(snapshots,list) or not fixture_id:
        raise ValueError("INVALID_INPUT")
    valid=[]
    rejected=[]
    for item in snapshots:
        if not isinstance(item,dict):
            rejected.append({"reason":"INVALID_SNAPSHOT"})
            continue
        source=item.get("source")
        if item.get("fixture_id")!=fixture_id:
            rejected.append({"source":source,"reason":"FIXTURE_ID_MISMATCH"})
            continue
        observed=_parse(item.get("observed_at"))
        updated=_parse(item.get("updated_at"))
        if observed is None or updated is None or updated>observed:
            rejected.append({"source":source,"reason":"UNVERIFIABLE_TIMESTAMP"})
            continue
        if not all(type(item.get(k)) is int and item[k]>=0 for k in ("home_score","away_score")):
            rejected.append({"source":source,"reason":"INVALID_SCORE"})
            continue
        valid.append((updated,item))
    valid.sort(key=lambda x:x[0],reverse=True)
    if not valid:
        return {"status":"UNVERIFIED","latest":None,"rejected":rejected}
    newest=valid[0][1]
    tied=[x[1] for x in valid if x[0]==valid[0][0]]
    if len({(x["home_score"],x["away_score"]) for x in tied})>1:
        return {"status":"CONFLICT","latest":None,"rejected":rejected}
    return {"status":"TIMESTAMP_ORDERED_NOT_INDEPENDENTLY_VERIFIED",
            "latest":{"source":newest.get("source"),"updated_at":newest["updated_at"],
                      "home_score":newest["home_score"],"away_score":newest["away_score"]},
            "rejected":rejected}
