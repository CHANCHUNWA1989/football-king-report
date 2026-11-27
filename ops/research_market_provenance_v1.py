"""Fail-closed provenance gate for pre-match research market snapshots.

No live feed, no bookmaker connectivity and no executable market verification.
This is an auditable validation interface only.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

@dataclass(frozen=True)
class Quote:
    source: str
    bookmaker: str
    event_id: str
    market: str
    selection: str
    line: float
    decimal_odds: float
    observed_at: datetime
    kickoff_at: datetime
    is_executable: bool = False

def audit_quotes(quotes: Sequence[Quote], *, now: datetime,
                 max_age_seconds: int=300, require_independent_sources: int=2) -> dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("aware current timestamp required")
    if not isinstance(max_age_seconds,int) or max_age_seconds<=0 or require_independent_sources<2:
        raise ValueError("invalid audit policy")
    accepted=[]
    rejected=[]
    for q in quotes:
        reason=None
        if not q.source.strip() or not q.bookmaker.strip() or not q.event_id.strip():
            reason="MISSING_PROVENANCE"
        elif q.market not in ("handicap","totals") or q.selection not in (
                ("home","away") if q.market=="handicap" else ("over","under")):
            reason="INVALID_MARKET"
        elif not isinstance(q.line,(int,float)) or isinstance(q.line,bool) or not math.isfinite(q.line) or abs(q.line*4-round(q.line*4))>1e-9:
            reason="INVALID_LINE"
        elif not isinstance(q.decimal_odds,(int,float)) or isinstance(q.decimal_odds,bool) or not math.isfinite(q.decimal_odds) or q.decimal_odds<=1:
            reason="INVALID_ODDS"
        elif q.observed_at.tzinfo is None or q.observed_at.utcoffset() is None or q.kickoff_at.tzinfo is None or q.kickoff_at.utcoffset() is None:
            reason="NAIVE_TIME"
        elif q.observed_at>now or q.observed_at>=q.kickoff_at or now>=q.kickoff_at:
            reason="NOT_PREMATCH"
        elif (now-q.observed_at).total_seconds()>max_age_seconds:
            reason="STALE_QUOTE"
        if reason:
            rejected.append({"event_id":q.event_id,"reason":reason})
        else:
            accepted.append(q)
    groups={}
    for q in accepted:
        key=(q.event_id,q.market,q.selection,q.line)
        groups.setdefault(key,[]).append(q)
    independent={str(key):len(set(q.source for q in group)) for key,group in groups.items()}
    qualified=[str(key) for key,group in groups.items() if len(set(q.source for q in group))>=require_independent_sources]
    # A multi-source match is not sufficient evidence that the price is executable.
    return {"status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
            "accepted":len(accepted),"rejected":rejected,
            "independent_sources_by_market":independent,
            "independent_market_keys":qualified,
            "verified_executable_ev":False,"qualified_for_production":False}
