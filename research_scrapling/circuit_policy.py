"""Deterministic research-only circuit-breaker reference policy.
No network requests, persistence, source switching or production activation.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from source_health import assess

COOLDOWN=timedelta(seconds=300)
MIN_INTERVAL=timedelta(seconds=30)
REQUIRED_SUCCESSES=3

@dataclass(frozen=True)
class State:
    domain: str
    last_checked: datetime
    reopen_until: datetime
    last_capture: datetime | None = None
    successes: int = 0
    phase: str = "OPEN"

def start(domain, now):
    if domain not in ("football","quant") or now.tzinfo is None:
        raise ValueError("domain and aware clock required")
    return State(domain,now,now+COOLDOWN)

def trip(state, now):
    return replace(state,last_checked=now,reopen_until=now+COOLDOWN,
                   successes=0,phase="OPEN")

def advance(state, doc, now):
    if now.tzinfo is None or now<=state.last_checked:
        return trip(state,state.last_checked)
    health=assess(state.domain,doc,now)
    if health["health"]!="HISTORICAL_METADATA_OK":
        return trip(state,now)
    capture=min(datetime.fromisoformat(x["captured_utc"].replace("Z","+00:00"))
                for x in doc["source_evidence"])
    if state.last_capture is not None and capture<=state.last_capture:
        return trip(state,now)
    if now<state.reopen_until:
        return replace(state,last_checked=now,last_capture=capture)
    if capture<state.reopen_until:
        return trip(state,now)
    if state.last_capture is not None and capture-state.last_capture<MIN_INTERVAL:
        return replace(state,last_checked=now,last_capture=capture)
    n=min(REQUIRED_SUCCESSES,state.successes+1)
    return replace(state,last_checked=now,last_capture=capture,successes=n,
                   phase="HISTORICAL_RESEARCH_READY" if n==REQUIRED_SUCCESSES else "HALF_OPEN")

def snapshot(state):
    return {"domain":state.domain,"phase":state.phase,"successes":state.successes,
            "reopen_until":state.reopen_until.isoformat(),"status":"HOLD",
            "production_recommendations":"DISABLED","live_trading":"DISABLED",
            "model_input_allowed":False,"automatic_failover_allowed":False,
            "policy_simulation_only":True}
