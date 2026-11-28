"""Fail-closed inventory for independent football evidence (research only).

No source URL, publisher name or claimed timestamp is treated as authentication.
This module deliberately cannot unlock production or count authenticated samples.
"""
from __future__ import annotations
from datetime import datetime, timezone
from urllib.parse import urlsplit
import re

SHA256=re.compile(r"^[0-9a-f]{64}$")
REQUIRED=("fixture_key","forecast_sha256","recorded_forecast_at",
          "kickoff_observations","publisher_provenance","market_snapshot")

def _time(value):
    if type(value) is not str:
        raise ValueError("timestamp required")
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)

def _source(item):
    if type(item) is not dict:
        raise ValueError("source must be object")
    url=item.get("url")
    if type(url) is not str:
        raise ValueError("source URL required")
    parsed=urlsplit(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("HTTPS public source URL required")
    if type(item.get("publisher")) is not str or not item["publisher"].strip():
        raise ValueError("publisher required")
    if type(item.get("upstream")) is not str or not item["upstream"].strip():
        raise ValueError("upstream attribution required")
    return item["upstream"].strip().casefold()

def inspect_external_evidence(candidate:dict)->dict:
    if type(candidate) is not dict or any(k not in candidate for k in REQUIRED):
        raise ValueError("incomplete evidence inventory")
    if type(candidate["fixture_key"]) is not str or not candidate["fixture_key"].strip():
        raise ValueError("fixture key required")
    if type(candidate["forecast_sha256"]) is not str or not SHA256.fullmatch(candidate["forecast_sha256"]):
        raise ValueError("invalid forecast digest")
    forecast_at=_time(candidate["recorded_forecast_at"])
    kickoff=candidate["kickoff_observations"]
    provenance=candidate["publisher_provenance"]
    market=candidate["market_snapshot"]
    if type(kickoff) is not list or len(kickoff)<2:
        raise ValueError("two kickoff observations required")
    if type(provenance) is not list or len(provenance)<2:
        raise ValueError("two provenance observations required")
    kickoff_upstreams=[]
    claimed_kickoffs=[]
    for obs in kickoff:
        kickoff_upstreams.append(_source(obs))
        if _time(obs.get("observed_at"))>forecast_at:
            raise ValueError("kickoff observation acquired after forecast")
        claimed_kickoffs.append(_time(obs.get("claimed_kickoff_at")))
    provider_upstreams=[_source(obs) for obs in provenance]
    for obs in provenance:
        if _time(obs.get("captured_at"))>forecast_at:
            raise ValueError("provenance captured after forecast")
    if type(market) is not dict:
        raise ValueError("market snapshot required")
    _source(market)
    market_at=_time(market.get("captured_at"))
    if market_at>forecast_at:
        raise ValueError("market snapshot after forecast cutoff")
    if len(set(claimed_kickoffs))!=1:
        raise ValueError("conflicting claimed kickoff timestamps")
    if not all(value>forecast_at for value in claimed_kickoffs):
        raise ValueError("forecast not before claimed kickoff")
    independent_claims=(len(set(kickoff_upstreams))>=2 and len(set(provider_upstreams))>=2)
    return {"schema":"external-evidence-inventory-v1","fixture_key":candidate["fixture_key"],
            "inventory_complete":True,"distinct_upstream_claims":independent_claims,
            "independence_authenticated":False,"actual_kickoff_authenticated":False,
            "market_same_cutoff_proven":False,"authenticated_samples":0,
            "model_promotion_allowed":False,"production_recommendations":"DISABLED",
            "status":"HOLD",
            "next_action":"Independently verify upstream identity, kickoff and immutable timestamps"}
