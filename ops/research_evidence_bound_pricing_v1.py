"""Research-only evidence-bound pricing; fail closed on unmatched market quotes."""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime
from typing import Sequence
from ops.research_market_provenance_v1 import Quote,audit_quotes
from ops.research_unified_pricing_v1 import unified_research_pricing

def evidence_bound_pricing(*, event_id: str, home_xg: float, away_xg: float,
                           quotes: Sequence[Quote], now: datetime,
                           handicap_line: float, totals_line: float,
                           dc_rho: float | None=None) -> dict:
    if not event_id or not event_id.strip():
        raise ValueError("missing event ID")
    audit=audit_quotes(quotes,now=now)
    expected={
        ("handicap","home"):handicap_line,
        ("handicap","away"):handicap_line,
        ("totals","over"):totals_line,
        ("totals","under"):totals_line}
    def valid_quote(q: Quote) -> bool:
        return (bool(q.source.strip()) and bool(q.bookmaker.strip()) and
                bool(q.upstream_provider.strip()) and
                isinstance(q.decimal_odds,(int,float)) and
                not isinstance(q.decimal_odds,bool) and
                math.isfinite(q.decimal_odds) and q.decimal_odds>1 and
                q.observed_at.tzinfo is not None and
                q.observed_at.utcoffset() is not None and
                q.kickoff_at.tzinfo is not None and
                q.kickoff_at.utcoffset() is not None and
                q.observed_at<=now and q.observed_at<q.kickoff_at and
                now<q.kickoff_at and
                (now-q.observed_at).total_seconds()<=300)

    def independent_pair(peers: list[Quote]) -> bool:
        return any(a.source.strip().casefold()!=b.source.strip().casefold()
                   and a.upstream_provider.strip().casefold()!=
                       b.upstream_provider.strip().casefold()
                   for i,a in enumerate(peers) for b in peers[i+1:])

    chosen={}
    for (market,selection),line in expected.items():
        eligible=[q for q in quotes if q.event_id==event_id and
                  q.market==market and q.selection==selection and q.line==line
                  and valid_quote(q)]
        if not eligible:
            raise ValueError("missing required market selection")
        # Require two distinct publishers and two distinct upstream feeds,
        # one bookmaker, same exact odds and <=60s timestamp spread.
        candidates=[]
        for anchor in eligible:
            peers=[q for q in eligible if
                   q.bookmaker.strip().casefold()==anchor.bookmaker.strip().casefold()
                   and q.kickoff_at==anchor.kickoff_at
                   and q.decimal_odds==anchor.decimal_odds
                   and abs((q.observed_at-anchor.observed_at).total_seconds())<=60
                   and q.observed_at<=now and q.observed_at<q.kickoff_at
                   and now<q.kickoff_at and
                   (now-q.observed_at).total_seconds()<=300]
            if independent_pair(peers):
                candidates.append((anchor,peers))
        if not candidates:
            raise ValueError("no strict quote consensus")
        # Never silently choose among different bookmaker/price snapshots.
        identities={(a.bookmaker.strip().casefold(),a.decimal_odds) for a,_ in candidates}
        if len(identities)!=1:
            raise ValueError("ambiguous bookmaker or price")
        chosen[(market,selection)]=candidates[0][0]
    kickoffs={q.kickoff_at for q in chosen.values()}
    bookmakers={q.bookmaker.strip().casefold() for q in chosen.values()}
    if len(kickoffs)!=1 or len(bookmakers)!=1:
        raise ValueError("inconsistent kickoff or bookmaker across selections")
    # A coherent four-market snapshot must not combine observations from
    # different points in a moving market. Check the complete chosen batch.
    selected_times=[q.observed_at for q in chosen.values()]
    if (max(selected_times)-min(selected_times)).total_seconds()>60:
        raise ValueError("cross-market quote snapshot exceeds 60 seconds")
    pricing=unified_research_pricing(
        home_xg,away_xg,handicap_line=handicap_line,totals_line=totals_line,
        handicap_home_odds=chosen["handicap","home"].decimal_odds,
        handicap_away_odds=chosen["handicap","away"].decimal_odds,
        over_odds=chosen["totals","over"].decimal_odds,
        under_odds=chosen["totals","under"].decimal_odds,dc_rho=dc_rho)
    manifest=[{"market":m,"selection":s,"line":expected[m,s],
               "decimal_odds":chosen[m,s].decimal_odds,
               "bookmaker":chosen[m,s].bookmaker.strip().casefold()}
              for m,s in expected]
    pricing["quote_manifest_sha256"]=hashlib.sha256(
        json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    pricing["market_audit"]=audit
    pricing["evidence_bound_research_prices"]=True
    pricing["verified_executable_ev"]=False
    pricing["qualified_for_production"]=False
    pricing["production_recommendations"]="DISABLED"
    return pricing
