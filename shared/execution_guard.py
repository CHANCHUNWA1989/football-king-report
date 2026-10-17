"""Fail-closed execution gate: research and paper mode only.

This module deliberately has NO broker, exchange, or sportsbook adapter.
A human approval cannot override the current live-execution lock.
"""
from datetime import datetime, timezone

ALLOWED_MODES = frozenset({"RESEARCH_ONLY", "PAPER"})
LIVE_EXECUTION_ENABLED = False

def validate_proposal(proposal):
    if not isinstance(proposal, dict):
        raise ValueError("proposal must be a dict")
    required = ("proposal_id", "system", "mode", "created_at", "expires_at", "instrument", "side", "amount")
    if any(k not in proposal for k in required):
        raise ValueError("missing proposal fields")
    if proposal["system"] not in ("football", "basketball", "quant"):
        raise ValueError("unsupported system")
    if proposal["mode"] not in ALLOWED_MODES:
        raise ValueError("live execution is disabled")
    for k in ("proposal_id", "instrument", "side"):
        if not isinstance(proposal[k], str) or not proposal[k].strip():
            raise ValueError("invalid " + k)
    amount = proposal["amount"]
    if type(amount) not in (int, float) or not (0 < amount < float("inf")):
        raise ValueError("invalid amount")
    try:
        created = datetime.fromisoformat(proposal["created_at"].replace("Z", "+00:00"))
        expiry = datetime.fromisoformat(proposal["expires_at"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("invalid timestamps") from exc
    if created.tzinfo is None or expiry.tzinfo is None or expiry <= created:
        raise ValueError("invalid expiry")
    return True

def authorize_execution(proposal, approval=None, now=None):
    """Never authorizes real-money execution, even with a supplied approval."""
    validate_proposal(proposal)
    if proposal["mode"] == "RESEARCH_ONLY":
        return {"allowed": False, "reason": "RESEARCH_ONLY"}
    if LIVE_EXECUTION_ENABLED is False:
        return {"allowed": False, "reason": "LIVE_EXECUTION_DISABLED"}
    raise RuntimeError("unexpected live execution state")
