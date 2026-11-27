"""Research-only post-match audit with two independent result publishers.

Uses an immutable forecast record, verifies its digest, and settles only when
two independent exact full-time scores agree. Never promotes production.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from ops.research_evidence_ledger_v1 import verify_record
from ops.research_asian_settlement_v1 import asian_ev

@dataclass(frozen=True)
class ResultEvidence:
    event_id: str
    publisher: str
    observed_at: datetime
    home_goals: int
    away_goals: int
    is_final: bool

def audit_settlement(forecast: dict, results: Sequence[ResultEvidence]) -> dict:
    if not verify_record(forecast) or forecast.get("status")!="HOLD":
        raise ValueError("forecast evidence digest invalid")
    event=forecast["event_id"]
    kickoff=datetime.fromisoformat(forecast["kickoff_at"])
    valid=[]
    for r in results:
        if r.event_id!=event or not r.publisher.strip() or not r.is_final:
            continue
        if r.observed_at.tzinfo is None or r.observed_at.utcoffset() is None or r.observed_at<=kickoff:
            continue
        if any(type(g) is not int or not 0<=g<=20 for g in (r.home_goals,r.away_goals)):
            continue
        valid.append(r)
    by_score={}
    for r in valid:
        by_score.setdefault((r.home_goals,r.away_goals),set()).add(r.publisher)
    agreed=[score for score,pubs in by_score.items() if len(pubs)>=2]
    status="SETTLED_RESEARCH" if len(agreed)==1 and len(by_score)==1 else "HOLD"
    output={"schema":"football-king-research-settlement-v1",
            "event_id":event,"forecast_sha256":forecast["sha256"],
            "status":status,"production_recommendations":"DISABLED",
            "verified_positive_ev":False,"qualified_for_production":False,
            "final_score":list(agreed[0]) if status=="SETTLED_RESEARCH" else None,
            "reason":("TWO_INDEPENDENT_FINAL_SCORES" if status=="SETTLED_RESEARCH"
                      else "MISSING_OR_CONFLICTING_FINAL_SCORES")}
    if status=="SETTLED_RESEARCH":
        h,a=agreed[0]
        outcome="home" if h>a else ("away" if h<a else "draw")
        p=forecast["one_x_two"]
        output["observed_outcome"]=outcome
        output["brier"]=sum((p[k]-float(k==outcome))**2 for k in ("home","draw","away"))
        # Market prices are deliberately not settled here: the record does not
        # prove its odds were executable or its quotes matched those prices.
        output["asian_market_settlements"]="NOT_VERIFIED"
    canonical=json.dumps(output,sort_keys=True,separators=(",",":"),allow_nan=False)
    output["sha256"]=hashlib.sha256(canonical.encode()).hexdigest()
    return output
