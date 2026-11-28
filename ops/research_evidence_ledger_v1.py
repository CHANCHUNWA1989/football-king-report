"""Research-only evidence ledger tying forecast, quote audit and settlement.

Records are deterministic and tamper-evident, but not externally notarized.
No production betting, no external feed and no verified positive EV claims.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from typing import Sequence
from ops.research_unified_pricing_v1 import unified_research_pricing
from ops.research_market_provenance_v1 import Quote,audit_quotes

def _iso(t: datetime) -> str:
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return t.isoformat()

def research_evidence_record(*, event_id: str, forecast_at: datetime,
                             kickoff_at: datetime, home_xg: float, away_xg: float,
                             quotes: Sequence[Quote], now: datetime,
                             handicap_line: float, totals_line: float,
                             handicap_home_odds: float, handicap_away_odds: float,
                             over_odds: float, under_odds: float) -> dict:
    if not event_id.strip():
        raise ValueError("invalid fixture metadata")
    _iso(forecast_at)
    _iso(kickoff_at)
    _iso(now)
    # Compare actual instants, not ISO lexical offsets.
    if forecast_at>=kickoff_at or now>=kickoff_at or forecast_at>now:
        raise ValueError("forecast must precede kickoff and audit")
    if any(q.event_id!=event_id or q.kickoff_at!=kickoff_at for q in quotes):
        raise ValueError("quote event or kickoff mismatch")
    pricing=unified_research_pricing(home_xg,away_xg,
        handicap_line=handicap_line,totals_line=totals_line,
        handicap_home_odds=handicap_home_odds,handicap_away_odds=handicap_away_odds,
        over_odds=over_odds,under_odds=under_odds)
    audit=audit_quotes(quotes,now=now)
    payload={"schema":"football-king-research-evidence-v1",
             "event_id":event_id,"forecast_at":_iso(forecast_at),
             "kickoff_at":_iso(kickoff_at),"audit_at":_iso(now),
             "model":{"home_xg":home_xg,"away_xg":away_xg},
             "one_x_two":pricing["one_x_two"],
             "market_expected_returns":{k:v["expected_net_return"] for k,v in pricing["markets"].items()},
             "market_audit":audit,
             "status":"HOLD","production_recommendations":"DISABLED",
             "verified_positive_ev":False,"qualified_for_production":False}
    canonical=json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False)
    payload["sha256"]=hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload

def verify_record(record: dict) -> bool:
    body={k:v for k,v in record.items() if k!="sha256"}
    try:
        canonical=json.dumps(body,sort_keys=True,separators=(",",":"),allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()==record.get("sha256")
    except (TypeError,ValueError):
        return False
