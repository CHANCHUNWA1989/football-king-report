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
    upstream_provider: str = ""

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
    def lineage(q: Quote) -> str:
        # A publisher cannot count twice under aliases. Missing upstream
        # lineage is not proof of independence, so it never qualifies.
        return q.upstream_provider.strip().casefold()
    independent={str(key):len({lineage(q) for q in group if lineage(q)})
                 for key,group in groups.items()}
    qualified=[str(key) for key,group in groups.items()
               if len({lineage(q) for q in group if lineage(q)})>=require_independent_sources
               and len({q.source.strip().casefold() for q in group if lineage(q)})>=require_independent_sources]
    # A source-lineage count alone is not price consensus. Keep this separate
    # from the legacy lineage-qualified keys for backward compatibility.
    # Compare only quotes from the same bookmaker and normalized upstream.
    consensus=[]
    for key,group in groups.items():
        by_bookmaker={}
        for q in group:
            if lineage(q):
                by_bookmaker.setdefault(q.bookmaker.strip().casefold(),[]).append(q)
        for bookmaker,book_quotes in by_bookmaker.items():
            # Independent upstream and publisher identities must be present.
            for anchor in book_quotes:
                matching=[q for q in book_quotes
                          if abs(q.decimal_odds-anchor.decimal_odds)<=1e-9
                          and abs((q.observed_at-anchor.observed_at).total_seconds())<=60]
                if (len({lineage(q) for q in matching})>=require_independent_sources
                    and len({q.source.strip().casefold() for q in matching})>=require_independent_sources):
                    consensus.append({"market_key":str(key),"bookmaker":bookmaker,
                                      "decimal_odds":anchor.decimal_odds,
                                      "publisher_count":len({q.source.strip().casefold() for q in matching}),
                                      "upstream_count":len({lineage(q) for q in matching})})
                    break
    # A multi-source match is not sufficient evidence that the price is executable.
    return {"status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
            "accepted":len(accepted),"rejected":rejected,
            "independent_sources_by_market":independent,
            "independent_market_keys":qualified,
            "strict_price_consensus":consensus,
            "verified_executable_ev":False,"qualified_for_production":False}
