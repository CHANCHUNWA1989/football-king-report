"""Fail-closed independent provider entitlement check for live research.

Caller-supplied registry is a trusted local configuration, never provider JSON.
This module does not verify legal rights itself; an administrator must confirm
contract coverage before enabling a provider in the registry.
"""
from datetime import datetime, timezone
from live_quote_gate import _utc
from live_provider_adapter import normalize_and_admit


def admit_with_registry(raw, registry, *, now=None):
    hold = {"status": "HOLD", "reason": "PROVIDER_ENTITLEMENT_NOT_VERIFIED",
            "production_recommendations": "DISABLED", "observations": []}
    if not isinstance(raw, dict) or not isinstance(registry, dict):
        return hold
    match, market = raw.get("match"), raw.get("market")
    if not isinstance(match, dict) or not isinstance(market, dict):
        return hold
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None:
        return hold
    current = current.astimezone(timezone.utc)
    score_provider, odds_provider = match.get("provider"), market.get("provider")
    for name, capability in ((score_provider, "live_scores"),
                             (odds_provider, "live_odds")):
        if not isinstance(name, str) or not name.strip():
            return hold
        rights = registry.get(name)
        if (not isinstance(rights, dict)
                or rights.get("admin_verified") is not True
                or rights.get(capability) is not True
                or rights.get("research_use") is not True):
            return hold
        expires = _utc(rights.get("expires_at_utc"))
        verified = _utc(rights.get("verified_at_utc"))
        if (expires is None or verified is None or verified > current
                or expires <= current or verified >= expires):
            return hold
    return normalize_and_admit(raw, now=now)
