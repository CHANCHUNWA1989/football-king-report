"""V34: isolated prematch evidence and scenario diagnostics; never release signals."""
from dataclasses import dataclass
from datetime import datetime
from itertools import product
import math
from .research_evidence_bound_pricing_v1 import evidence_bound_pricing

@dataclass(frozen=True)
class Forecast:
    event_id: str
    kickoff: datetime
    observed: datetime
    model: str
    upstream: str
    home: float
    away: float

def aware(t):
    return isinstance(t, datetime) and t.tzinfo is not None and t.utcoffset() is not None

def audit(*, event_id, kickoff, now, forecasts, quotes, handicap_line, totals_line,
          delta=0.15):
    """Finite scenario grid, not a confidence interval or calibrated uncertainty."""
    result={"schema":"unified-prematch-audit-v34","status":"HOLD",
            "production_recommendations":"DISABLED","verified_executable_ev":False,
            "qualified_for_production":False,"diagnostics":{}}
    try:
        if not event_id.strip() or not all(map(aware,(kickoff,now))) or now>=kickoff:
            raise ValueError("invalid prematch event clock")
        if isinstance(delta,bool) or not isinstance(delta,(int,float)) or not math.isfinite(delta) or not 0<delta<=0.5:
            raise ValueError("invalid stress delta")
        if not 2<=len(forecasts)<=8 or not 1<=len(quotes)<=128:
            raise ValueError("invalid evidence count")
        models=set()
        upstream=set()
        for f in forecasts:
            if f.event_id!=event_id or not aware(f.kickoff) or f.kickoff!=kickoff or not aware(f.observed):
                raise ValueError("forecast event mismatch")
            if f.observed>now or (now-f.observed).total_seconds()>86400:
                raise ValueError("future or stale forecast")
            model,feed=f.model.strip().casefold(),f.upstream.strip().casefold()
            if not model or not feed or model in models or feed in upstream:
                raise ValueError("duplicate or missing forecast lineage")
            models.add(model)
            upstream.add(feed)
            for rate in (f.home,f.away):
                if isinstance(rate,bool) or not isinstance(rate,(int,float)) or not math.isfinite(rate) or not delta<rate<=10-delta:
                    raise ValueError("invalid stress rate")
        if any(q.event_id!=event_id or not aware(q.kickoff_at) or q.kickoff_at!=kickoff for q in quotes):
            raise ValueError("quote event mismatch")
        evs={}
        manifests=set()
        for f in forecasts:
            for dh,da in product((-delta,0,delta),repeat=2):
                p=evidence_bound_pricing(event_id=event_id,home_xg=f.home+dh,away_xg=f.away+da,
                    quotes=quotes,now=now,handicap_line=handicap_line,totals_line=totals_line)
                manifests.add(p["quote_manifest_sha256"])
                for key,market in p["markets"].items():
                    v=market["expected_net_return"]
                    if not math.isfinite(v):
                        raise ValueError("invalid diagnostic")
                    evs.setdefault(key,[]).append(v)
        if len(manifests)!=1:
            raise ValueError("inconsistent quote manifest")
        result.update({"scenario_count":9*len(forecasts),"quote_manifest_sha256":next(iter(manifests)),
                       "diagnostics":{k:{"min":min(v),"max":max(v),"count":len(v),
                       "all_scenarios_positive":min(v)>0} for k,v in evs.items()},
                       "source_identity_authenticated":False,
                       "uncertainty_calibrated":False,"audit_completed":True})
    except (ValueError,TypeError,AttributeError,KeyError,OverflowError) as exc:
        result.update({"audit_completed":False,"reason":str(exc)})
    return result
