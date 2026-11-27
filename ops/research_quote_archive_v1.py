"""Canonical research quote evidence snapshot; no independent timestamp authority.

Records the exact quote rows used in evidence-bound research pricing. Recompute
the digest to detect accidental changes; never claim external source authenticity.
"""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime
from typing import Sequence
from ops.research_market_provenance_v1 import Quote
from ops.research_evidence_bound_pricing_v1 import evidence_bound_pricing

def _canonical(obj: dict) -> str:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)

def freeze_pricing_evidence(*, event_id: str, home_xg: float, away_xg: float,
                            quotes: Sequence[Quote], now: datetime,
                            handicap_line: float, totals_line: float,
                            dc_rho: float | None=None) -> dict:
    ordered_quotes=sorted(quotes,key=lambda q:(q.market,q.selection,q.line,
        q.bookmaker.strip().casefold(),q.decimal_odds,q.source.strip().casefold(),
        q.upstream_provider.strip().casefold(),q.observed_at.isoformat()))
    result=evidence_bound_pricing(event_id=event_id,home_xg=home_xg,
        away_xg=away_xg,quotes=ordered_quotes,now=now,handicap_line=handicap_line,
        totals_line=totals_line,dc_rho=dc_rho)
    # Capture every input quote, not only an aggregate price or source count.
    records=[dict(source=q.source,upstream_provider=q.upstream_provider,
                  bookmaker=q.bookmaker,event_id=q.event_id,market=q.market,
                  selection=q.selection,line=q.line,decimal_odds=q.decimal_odds,
                  observed_at=q.observed_at.isoformat(),
                  kickoff_at=q.kickoff_at.isoformat(),is_executable=q.is_executable)
             for q in ordered_quotes]
    payload={"schema":"football-king-research-quote-archive-v1",
             "event_id":event_id,"frozen_at":now.isoformat(),
             "model":{"home_xg":home_xg,"away_xg":away_xg,"dc_rho":dc_rho},
             "lines":{"handicap":handicap_line,"totals":totals_line},
             "quotes":sorted(records,key=_canonical),
             "pricing":result,"status":"HOLD",
             "production_recommendations":"DISABLED",
             "qualified_for_production":False}
    payload["sha256"]=hashlib.sha256(_canonical(payload).encode()).hexdigest()
    return payload

def verify_pricing_evidence(record: dict) -> bool:
    try:
        if not isinstance(record,dict) or record.get("status")!="HOLD":
            return False
        digest=record["sha256"]
        if not isinstance(digest,str) or len(digest)!=64:
            return False
        payload={k:v for k,v in record.items() if k!="sha256"}
        if hashlib.sha256(_canonical(payload).encode()).hexdigest()!=digest:
            return False
        if payload.get("qualified_for_production") is not False:
            return False
        if payload.get("production_recommendations")!="DISABLED":
            return False
        from datetime import datetime
        quotes=[Quote(source=q["source"],upstream_provider=q["upstream_provider"],
            bookmaker=q["bookmaker"],event_id=q["event_id"],market=q["market"],
            selection=q["selection"],line=q["line"],decimal_odds=q["decimal_odds"],
            observed_at=datetime.fromisoformat(q["observed_at"]),
            kickoff_at=datetime.fromisoformat(q["kickoff_at"]),
            is_executable=q["is_executable"]) for q in payload["quotes"]]
        model=payload["model"]
        expected=evidence_bound_pricing(event_id=payload["event_id"],
            home_xg=model["home_xg"],away_xg=model["away_xg"],
            quotes=quotes,now=datetime.fromisoformat(payload["frozen_at"]),
            handicap_line=payload["lines"]["handicap"],
            totals_line=payload["lines"]["totals"],dc_rho=model["dc_rho"])
        return _canonical(expected)==_canonical(payload["pricing"])
    except (ValueError,KeyError,TypeError,OverflowError,AttributeError):
        return False
