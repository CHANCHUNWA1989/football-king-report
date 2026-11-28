"""Offline checkpoint connection target binding; no socket is opened."""
from __future__ import annotations
import ipaddress
from ops.research_checkpoint_dns_policy_v1 import inspect_checkpoint_dns_answers

def inspect_checkpoint_connection_binding(locator:str, dns_answers:list[str],
                                          connection_ip:str)->dict:
    inspect_checkpoint_dns_answers(locator,dns_answers)
    if type(connection_ip) is not str:
        raise ValueError("connection IP required")
    try:
        target=ipaddress.ip_address(connection_ip)
        allowed={ipaddress.ip_address(address) for address in dns_answers}
    except ValueError as exc:
        raise ValueError("invalid connection IP") from exc
    if target not in allowed:
        raise ValueError("connection IP differs from approved DNS answers")
    return {"connection_target_matches_approved_answers":True,
            "connection_pinned_to_answers":False,
            "socket_connection_performed":False,
            "tls_peer_authenticated":False,
            "dns_resolution_verified":False,
            "checkpoint_externally_retrieved":False,
            "publisher_independence_authenticated":False,
            "status":"HOLD","model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
