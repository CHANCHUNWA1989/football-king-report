"""Strict whole-snapshot comparison for research; publisher labels are untrusted.
No network, authentication, trading, or production promotion.
"""
from hashlib import sha256
import json
from .research_unified_snapshot_audit_v1 import audit, _time, _odds, _number, MAX_AGE_SECONDS

MAX_SPREAD = 60
def _label(value):
    if not isinstance(value,str) or not value.strip() or len(value)>200:
        raise ValueError("invalid label")
    return value.strip().casefold()

def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)

def _market_rows(rows):
    if not isinstance(rows,list) or len(rows)>12:
        raise ValueError("invalid market rows")
    out={}
    for row in rows:
        if not isinstance(row,dict) or set(row)!={"market","selection","line","decimal_odds"}:
            raise ValueError("invalid market row")
        market,selection=row["market"],row["selection"]
        if market not in ("handicap","totals") or selection not in (
                ("home","away") if market=="handicap" else ("over","under")):
            raise ValueError("invalid market selection")
        line=_number(row["line"],-20 if market=="handicap" else 0,20)
        if line*4!=round(line*4):
            raise ValueError("invalid quarter line")
        key=(market,selection,line)
        if key in out:
            raise ValueError("duplicate market selection")
        out[key]=_odds(row["decimal_odds"])
    for market,selection,line in out:
        counterpart={"home":"away","away":"home","over":"under","under":"over"}[selection]
        if (market,counterpart,line) not in out:
            raise ValueError("unpaired Asian market")
    return [{"market":m,"selection":s,"line":l,"decimal_odds":p}
            for (m,s,l),p in sorted(out.items())]

def _envelope(raw, *, now, kickoff, fixture_id):
    expected={"publisher","upstream","bookmaker","fixture_id","kickoff","observed_at","odds","asian"}
    if not isinstance(raw,dict) or set(raw)!=expected:
        raise ValueError("invalid envelope schema")
    if raw["fixture_id"]!=fixture_id or _time(raw["kickoff"])!=kickoff:
        raise ValueError("fixture or kickoff mismatch")
    t=_time(raw["observed_at"])
    if not t<=now<kickoff or (now-t).total_seconds()>MAX_AGE_SECONDS:
        raise ValueError("stale or non-prematch quote")
    prices=raw["odds"]
    if not isinstance(prices,dict) or set(prices)!={"home","draw","away"}:
        raise ValueError("incomplete 1X2")
    return {"publisher":_label(raw["publisher"]),"upstream":_label(raw["upstream"]),
            "bookmaker":_label(raw["bookmaker"]),"observed_at":t.isoformat(),
            "odds":{k:_odds(v) for k,v in prices.items()},"asian":_market_rows(raw["asian"])}

def compare_snapshots(*, fixture_id,kickoff,as_of,rates,rates_at,snapshots):
    out={"schema":"unified-snapshot-consensus-v2","status":"HOLD",
         "production_recommendations":"DISABLED","certified_ev":False,
         "source_authenticity_verified":False,"upstream_independence_verified":False,
         "independent_oos_proven":False,"model_promotion_allowed":False}
    try:
        if not isinstance(fixture_id,str) or not fixture_id.strip() or len(fixture_id)>200:
            raise ValueError("invalid fixture identity")
        now,k=_time(as_of),_time(kickoff)
        if not isinstance(snapshots,list) or len(snapshots)!=2:
            raise ValueError("exactly two snapshots required")
        a,b=[_envelope(s,now=now,kickoff=k,fixture_id=fixture_id) for s in snapshots]
        if a["publisher"]==b["publisher"] or a["upstream"]==b["upstream"]:
            raise ValueError("duplicate declared lineage")
        if any(a[key]!=b[key] for key in ("bookmaker","odds","asian")):
            raise ValueError("whole-snapshot price disagreement")
        observed=min(_time(a["observed_at"]),_time(b["observed_at"]))
        if abs((_time(a["observed_at"])-_time(b["observed_at"])).total_seconds())>MAX_SPREAD:
            raise ValueError("snapshot time disagreement")
        result=audit(fixture_id=fixture_id,kickoff=kickoff,as_of=as_of,
                     quote_at=observed.isoformat(),rates_at=rates_at,rates=rates,
                     odds=a["odds"],asian=a["asian"])
        if not result["structural_audit_passed"]:
            raise ValueError("invalid scenario")
        evidence={"fixture_id":fixture_id,"kickoff":k.isoformat(),"as_of":now.isoformat(),
                  "rates_at":_time(rates_at).isoformat(),"rates":list(rates),
                  "snapshots":sorted([a,b],key=lambda x:x["publisher"])}
        return {**out,"structural_consensus_passed":True,
                "snapshot_sha256":sha256(_canonical(evidence).encode()).hexdigest(),
                "scenario":result,"complete_asian_pairs":len(a["asian"])//2,
                "declared_distinct_labels_only":True}
    except (TypeError,ValueError,KeyError,AttributeError,OverflowError):
        return {**out,"structural_consensus_passed":False,
                "reason":"MISSING_CONFLICTING_OR_INVALID_SNAPSHOT"}
