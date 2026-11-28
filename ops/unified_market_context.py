"""Private market-context bridge for the existing unified shadow and market_pair outputs.

No new requests, quoted prices, EV, stake sizing or promotion. Source documents
are observations, not authenticated proof. Never substitute a backup quote.
"""
import argparse
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from .unified_shadow_integration import read_json, utc, SCHEMA as SHADOW_SCHEMA
except ImportError:  # direct script entry
    from unified_shadow_integration import read_json, utc, SCHEMA as SHADOW_SCHEMA

SCHEMA = "football-king-unified-market-context-v1"


def safe(doc, schema):
    return (isinstance(doc, dict) and doc.get("schema")==schema
            and doc.get("production_recommendations")=="DISABLED")


def age_ok(value, now, minutes):
    try:
        return timedelta(0)<=now-utc(value)<=timedelta(minutes=minutes)
    except (ValueError, TypeError, OverflowError):
        return False


def vector(values):
    if not isinstance(values, list) or len(values)!=3:
        raise ValueError("INVALID_VECTOR")
    if any(type(x) not in (int,float) or not math.isfinite(x)
           or not 0<=x<=1 for x in values) or abs(math.fsum(values)-1)>1e-5:
        raise ValueError("INVALID_VECTOR")
    return values


def readiness(unified, pairs, market, collection, bsd, tipsme, now):
    now=utc(now.isoformat())
    out={"schema":SCHEMA,"as_of_utc":now.isoformat(),"status":"HOLD",
         "production_recommendations":"DISABLED","recommendation_count":0,
         "executable_market_quotes":False,"positive_ev_verified":False,
         "source_identity_authenticated":False,"automatic_source_substitution":False,
         "new_api_calls":0,"research_only":True,"sources":{},"pairs":[],"rejected":{}}
    primary_ok=(safe(market,"football-king-market-consensus-v1")
                and market.get("status")=="RESEARCH_ONLY"
                and market.get("provider")=="the-odds-api.com/v4"
                and market.get("market")=="h2h"
                and market.get("raw_bookmaker_quotes_redistributed") is False
                and age_ok(market.get("as_of_utc"),now,120))
    quota_hold=(safe(collection,"football-king-free-market-collection-status-v1")
                and collection.get("collection_status")=="HOLD"
                and collection.get("collection_reason")=="FREE_QUOTA_GUARD")
    out["sources"]["primary"]={"fresh_research_snapshot":bool(primary_ok),
                                 "last_reported_quota_hold":bool(quota_hold)}
    out["sources"]["bsd"]={
        "fresh_status_observation":bool(safe(bsd,"football-king-bsd-free-research-v1")
          and age_ok(bsd.get("captured_utc"),now,120)),
        "last_reported_no_comparable_market":bool(safe(bsd,"football-king-bsd-free-research-v1")
          and bsd.get("status")=="NO_COMPARABLE_MARKET")}
    out["sources"]["tipsme"]={
        "fresh_status_observation":bool(safe(tipsme,"football-king-hkjc-tipsme-free-research-v1")
          and age_ok(tipsme.get("captured_utc"),now,120)),
        "last_reported_not_configured":bool(safe(tipsme,"football-king-hkjc-tipsme-free-research-v1")
          and tipsme.get("status")=="NOT_CONFIGURED"),
        "not_official_hkjc_quote":True}
    if not primary_ok:
        out["reason"]="NO_FRESH_PRIMARY_RESEARCH_CONSENSUS"
        return out
    if not (safe(unified,SHADOW_SCHEMA) and unified.get("status")=="HOLD"
            and unified.get("model_calibrated") is False
            and unified.get("positive_ev_verified") is False
            and unified.get("recommendation_count")==0
            and age_ok(unified.get("as_of_utc"),now,30)
            and isinstance(unified.get("rows"),list) and len(unified["rows"])<=3000
            and isinstance(pairs,dict) and pairs.get("production_recommendations")=="DISABLED"
            and pairs.get("status")=="RESEARCH_ONLY"
            and isinstance(pairs.get("comparisons"),list) and len(pairs["comparisons"])<=3000
            and type(pairs.get("matched_count")) is int and pairs["matched_count"]==len(pairs["comparisons"])):
        out["reason"]="NO_VALID_UNIFIED_PAIR_BATCH"
        return out
    def key(r, field):
        if not isinstance(r,dict):
            return None
        a,b=r.get("league"),r.get(field)
        return (a,b) if all(isinstance(v,str) and 0<len(v)<=250 for v in (a,b)) else None
    source_rows=unified["rows"]
    index=Counter(key(r,"event_id") for r in source_rows)
    unique={key(r,"event_id"):r for r in source_rows
            if key(r,"event_id") is not None and index[key(r,"event_id")]==1}
    pair_rows=pairs["comparisons"]
    identities=Counter(key(r,"forecast_event_id") for r in pair_rows)
    market_ids=Counter(key(r,"market_event_id") for r in pair_rows)
    market_events=market.get("events")
    if not isinstance(market_events,list) or len(market_events)>3000:
        out["reason"]="INVALID_MARKET_EVENT_BATCH"
        return out
    market_index=Counter(key(r,"source_event_id") for r in market_events)
    observations={key(r,"source_event_id"):r for r in market_events
                  if key(r,"source_event_id") is not None and market_index[key(r,"source_event_id")]==1}
    rejects=Counter()
    for row in pair_rows:
        try:
            ident=key(row,"forecast_event_id")
            mid=key(row,"market_event_id")
            if ident is None or mid is None or identities[ident]!=1 or market_ids[mid]!=1:
                raise ValueError("AMBIGUOUS_PAIR")
            model=unique[ident]
            obs=observations[mid]
            if (row.get("production_recommendations")!="DISABLED"
                or model.get("production_recommendations")!="DISABLED"
                or model.get("calibrated") is not False
                or row.get("available_for_betting") is not False
                or row.get("result") is not None or row.get("historical_outcome") is not None
                or obs.get("probabilities_are_no_vig_consensus") is not True
                or obs.get("prediction_or_value_bet") is not False):
                raise ValueError("UNSAFE_PAIR_STATE")
            pred,kick,snap,updated=(utc(row[k]) for k in
                ("prediction_utc","kickoff_utc","market_snapshot_utc","market_updated_utc"))
            if (pred!=utc(model["prediction_utc"]) or kick!=utc(model["kickoff_utc"])
                or snap!=utc(market["as_of_utc"]) or updated!=utc(obs["market_last_update_utc"])
                or utc(obs["kickoff_utc"])!=kick
                or not updated<=snap<=pred<=now<kick
                or now-updated>timedelta(minutes=120)
                or kick-now<=timedelta(minutes=10)):
                raise ValueError("PAIR_TIME_MISMATCH")
            p=vector([model["probabilities"][k] for k in ("p_home","p_draw","p_away")])
            legacy=vector(row["model"])
            if any(abs(a-b)>1e-7 for a,b in zip(legacy,vector(model["legacy_probabilities"]))):
                raise ValueError("MODEL_VECTOR_MISMATCH")
            m=vector(row["market"])
            observed=vector([obs[k] for k in ("p_home","p_draw","p_away")])
            if any(abs(a-b)>1e-7 for a,b in zip(m,observed)):
                raise ValueError("MARKET_VECTOR_MISMATCH")
            # Expanded matrix can differ from the legacy truncated vector.
            # Keep both as labelled probabilities, not estimated returns.
            out["pairs"].append({"league":ident[0],"event_id":ident[1],
                "prediction_utc":pred.isoformat(),"kickoff_utc":kick.isoformat(),
                "market_snapshot_utc":snap.isoformat(),
                "unified_model_probability":p,"legacy_model_probability":legacy,
                "market_no_vig_probability":m,
                "model_minus_consensus_probability":[a-b for a,b in zip(p,m)],
                "probability_difference_is_not_ev":True,
                "production_recommendations":"DISABLED"})
        except (KeyError,TypeError,ValueError,OverflowError,AttributeError):
            rejects["INVALID_OR_INELIGIBLE_PAIR"]+=1
    out["rejected"]=dict(rejects)
    out["reason"]="UNVERIFIED_CONSENSUS_COMPARISON_ONLY" if out["pairs"] else "NO_STRICT_SAME_FIXTURE_PAIR"
    return out


def main():
    p=argparse.ArgumentParser()
    for name in ("unified","pairs","market","collection","bsd","tipsme","output"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    def load(name):
        try:
            return read_json(getattr(a,name))
        except (OSError,ValueError,TypeError,RecursionError):
            return None
    out=readiness(*(load(name) for name in ("unified","pairs","market","collection","bsd","tipsme")),datetime.now(timezone.utc))
    dest=Path(a.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix(dest.suffix+".tmp")
    tmp.write_text(json.dumps(out,allow_nan=False,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(dest)
    print(json.dumps({"status":out["status"],"reason":out["reason"],"strict_pairs":len(out["pairs"])}))


if __name__=="__main__":
    main()
