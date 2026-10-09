"""Six research infrastructure capabilities: OCR adapter, provider failover,
settlement reconciliation, live stats, probability calibration, and quotas.

All external observations must be supplied by callers. No hidden credentials,
imaginary live feeds, fake OCR, or permission to publish betting picks.
"""
import hashlib
import math
from datetime import datetime, timezone

SCHEMA="football-king-six-capabilities-v1"

def _time(value):
    if not isinstance(value,str):
        raise ValueError("MISSING_TIMESTAMP")
    t=datetime.fromisoformat(value.replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return t.astimezone(timezone.utc)

def _fresh(value, now, seconds):
    try:
        age=(now-_time(value)).total_seconds()
        return -10<=age<=seconds
    except (ValueError,TypeError,OverflowError):
        return False

def _number(v,lo,hi):
    return type(v) in (int,float) and math.isfinite(v) and lo<=v<=hi

def ocr_adapter(image_bytes, extracted, *, now=None):
    """Ingest external OCR output, not perform OCR or verify text against pixels."""
    now=now or datetime.now(timezone.utc)
    blockers=[]
    if not isinstance(image_bytes,bytes) or not 0<len(image_bytes)<=15_000_000:
        raise ValueError("INVALID_IMAGE")
    digest=hashlib.sha256(image_bytes).hexdigest()
    if not isinstance(extracted,dict):
        raise ValueError("INVALID_OCR_OUTPUT")
    if extracted.get("image_sha256")!=digest:
        blockers.append("IMAGE_HASH_MISMATCH")
    if extracted.get("engine") not in ("tesseract","paddleocr","easyocr","human_review"):
        blockers.append("UNSUPPORTED_ENGINE")
    if not _fresh(extracted.get("observed_at_utc"),now,120):
        blockers.append("STALE_OCR")
    if not isinstance(extracted.get("event_id"),str) or not extracted["event_id"]:
        blockers.append("MISSING_EVENT_ID")
    for k in ("home_goals","away_goals"):
        if type(extracted.get(k)) is not int or not 0<=extracted[k]<=25:
            blockers.append("INVALID_"+k.upper())
    if not _number(extracted.get("minute"),0,125):
        blockers.append("INVALID_MINUTE")
    if not _number(extracted.get("confidence"),0,1):
        blockers.append("INVALID_CONFIDENCE")
    return {"status":"RESEARCH_ONLY" if not blockers else "HOLD",
            "blockers":blockers,"image_sha256":digest,
            "external_ocr_claim_only":True,"ocr_performed_here":False,
            "independent_fixture_match_verified":False}

def provider_failover(observations, *, event_id, league, now=None, max_age=120):
    """Select a fresh, identified observation; never combine incompatible events."""
    now=now or datetime.now(timezone.utc)
    if not isinstance(observations,list) or len(observations)>100:
        raise ValueError("INVALID_OBSERVATIONS")
    accepted=[]
    rejected={}
    for row in observations:
        if not isinstance(row,dict):
            rejected["INVALID_ROW"]=rejected.get("INVALID_ROW",0)+1
            continue
        reason=None
        if row.get("event_id")!=event_id or row.get("league")!=league:
            reason="IDENTITY_MISMATCH"
        elif not _fresh(row.get("observed_at_utc"),now,max_age):
            reason="STALE_SOURCE"
        elif not isinstance(row.get("provider"),str) or not row["provider"]:
            reason="UNKNOWN_PROVIDER"
        elif row.get("transport_error") not in (None, ""):
            reason="TRANSPORT_ERROR"
        elif row.get("http_status") == 429:
            reason="RATE_LIMITED"
        elif (row.get("http_status") is not None
              and (type(row["http_status"]) is not int
                   or not 200<=row["http_status"]<300)):
            reason="HTTP_ERROR"
        elif (row.get("quota_remaining") is not None
              and (type(row["quota_remaining"]) is not int
                   or row["quota_remaining"]<0)):
            reason="INVALID_QUOTA"
        elif row.get("quota_remaining") == 0:
            reason="QUOTA_EXHAUSTED"
        elif row.get("provider_authenticated") is not True:
            reason="UNVERIFIED_PROVIDER"
        if reason:
            rejected[reason]=rejected.get(reason,0)+1
        else:
            accepted.append(row)
    accepted.sort(key=lambda x:(_time(x["observed_at_utc"]),x["provider"]),reverse=True)
    # Several observations from one provider are not several independent fallbacks.
    distinct=[]
    seen_providers=set()
    for row in accepted:
        if row["provider"] in seen_providers:
            rejected["DUPLICATE_PROVIDER_OBSERVATION"]=rejected.get("DUPLICATE_PROVIDER_OBSERVATION",0)+1
            continue
        seen_providers.add(row["provider"])
        distinct.append(row)
    accepted=distinct
    return {"status":"RESEARCH_ONLY" if accepted else "HOLD",
            "selected_provider":accepted[0]["provider"] if accepted else None,
            "selected_observation":accepted[0] if accepted else None,
            "fallback_count":max(0,len(accepted)-1),
            "distinct_provider_count":len(accepted),"rejections":rejected,
            "provider_authentication_self_attested":True,
            "real_network_failover_verified":False}

def reconcile_settlement(predictions, results):
    """Cross-reference settled outcomes against exact event+market identifiers."""
    if not isinstance(predictions,list) or not isinstance(results,list):
        raise ValueError("INVALID_COLLECTION")
    verified={}
    for row in results:
        if not isinstance(row,dict):
            continue
        key=(row.get("event_id"),row.get("market"))
        if not all(isinstance(x,str) and x for x in key):
            continue
        if key in verified:
            verified[key]=None
        elif type(row.get("outcome")) is int and row["outcome"] in (0,1):
            verified[key]=row
    # A repeated (event, market) prediction must not inflate settled sample counts.
    prediction_counts={}
    for row in predictions:
        if isinstance(row,dict):
            key=(row.get("event_id"),row.get("market"))
            if all(isinstance(x,str) and x for x in key):
                prediction_counts[key]=prediction_counts.get(key,0)+1
    matched=[]
    for row in predictions:
        if not isinstance(row,dict):
            continue
        key=(row.get("event_id"),row.get("market"))
        if not all(isinstance(x,str) and x for x in key):
            continue
        if prediction_counts.get(key)!=1:
            continue
        settlement=verified.get(key)
        if settlement is None:
            continue
        try:
            if _time(row["prediction_created_at_utc"])>=_time(row["kickoff_utc"]):
                continue
            if _time(settlement["settled_at_utc"])<=_time(row["kickoff_utc"]):
                continue
        except (KeyError,ValueError,TypeError,OverflowError):
            continue
        matched.append({"event_id":key[0],"market":key[1],
                        "outcome":settlement["outcome"],
                        "settlement_source":settlement.get("provider"),
                        "independently_authenticated":False})
    return {"status":"RESEARCH_ONLY" if matched else "HOLD",
            "matched":matched,"matched_count":len(matched),
            "duplicate_prediction_keys":sum(n>1 for n in prediction_counts.values()),
            "independent_settlement_verified":False}

def live_stats(observations, *, event_id, now=None):
    now=now or datetime.now(timezone.utc)
    valid=[]
    for row in observations if isinstance(observations,list) else []:
        if not isinstance(row,dict) or row.get("event_id")!=event_id:
            continue
        if not _fresh(row.get("observed_at_utc"),now,180):
            continue
        if not all(_number(row.get(k),0,100) for k in
                   ("home_shots","away_shots","home_shots_on_target","away_shots_on_target",
                    "home_red_cards","away_red_cards")):
            continue
        if row["home_shots_on_target"]>row["home_shots"] or row["away_shots_on_target"]>row["away_shots"]:
            continue
        xg=(row.get("home_xg"),row.get("away_xg"))
        if any(v is not None and not _number(v,0,20) for v in xg):
            continue
        valid.append(row)
    valid.sort(key=lambda x:_time(x["observed_at_utc"]),reverse=True)
    return {"status":"RESEARCH_ONLY" if valid else "HOLD",
            "latest":valid[0] if valid else None,
            "xg_available":bool(valid and all(valid[0].get(k) is not None for k in ("home_xg","away_xg"))),
            "independent_stats_verified":False}

def calibration(rows, *, min_samples=300, bins=10):
    if not isinstance(rows,list) or not 2<=bins<=20:
        raise ValueError("INVALID_CALIBRATION_INPUT")
    accepted=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        p,y=row.get("probability"),row.get("outcome")
        if _number(p,0,1) and type(y) is int and y in (0,1):
            accepted.append((float(p),y))
    groups=[]
    for i in range(bins):
        bucket=[(p,y) for p,y in accepted if min(int(p*bins),bins-1)==i]
        if bucket:
            groups.append({"bin":i,"n":len(bucket),
                           "predicted_mean":round(sum(p for p,_ in bucket)/len(bucket),6),
                           "observed_rate":round(sum(y for _,y in bucket)/len(bucket),6)})
    n=len(accepted)
    return {"status":"RESEARCH_ONLY" if n else "HOLD","samples":n,
            "brier":round(sum((p-y)**2 for p,y in accepted)/n,8) if n else None,
            "reliability_bins":groups,"sample_threshold_met":n>=min_samples,
            "out_of_sample_independently_verified":False,
            "calibration_verified":False}

def quota_health(providers, *, now=None):
    now=now or datetime.now(timezone.utc)
    if not isinstance(providers,list):
        raise ValueError("INVALID_PROVIDERS")
    rows=[]
    for p in providers:
        if not isinstance(p,dict) or not isinstance(p.get("provider"),str):
            continue
        remaining=p.get("remaining")
        limit=p.get("limit")
        if type(remaining) is not int or type(limit) is not int or not 0<=remaining<=limit or limit<=0:
            status="UNKNOWN"
        elif not _fresh(p.get("checked_at_utc"),now,3600):
            status="STALE"
        elif remaining==0:
            status="EXHAUSTED"
        elif remaining/limit<=0.1:
            status="LOW"
        else:
            status="HEALTHY"
        rows.append({"provider":p["provider"],"status":status,
                     "remaining":remaining if type(remaining) is int else None,
                     "limit":limit if type(limit) is int else None})
    return {"schema":SCHEMA,"providers":rows,
            "status":"HOLD" if not rows or any(x["status"]!="HEALTHY" for x in rows) else "RESEARCH_ONLY",
            "no_live_quota_api_called":True,"production_recommendations":"DISABLED"}
