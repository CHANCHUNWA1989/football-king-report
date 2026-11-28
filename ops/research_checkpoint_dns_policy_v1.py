"""Offline validation of supplied DNS answers. No DNS lookup or HTTP request occurs."""
from __future__ import annotations
import ipaddress
from ops.research_checkpoint_locator_policy_v1 import inspect_checkpoint_locator

def inspect_checkpoint_dns_answers(locator:str,addresses:list[str])->dict:
    inspect_checkpoint_locator(locator)
    if type(addresses) is not list or not addresses or len(addresses)>16:
        raise ValueError("one to sixteen DNS addresses required")
    seen=set()
    for address in addresses:
        if type(address) is not str or address!=address.strip():
            raise ValueError("invalid DNS address")
        try:
            ip=ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError("invalid DNS address") from exc
        if not ip.is_global or ip.is_multicast or ip.is_unspecified or ip.is_loopback or ip.is_link_local:
            raise ValueError("nonpublic DNS answer rejected")
        if ip.compressed in seen:
            raise ValueError("duplicate DNS address rejected")
        seen.add(ip.compressed)
    return {"dns_answer_policy_checked":True,"dns_resolution_performed":False,
            "dns_resolution_verified":False,"connection_pinned_to_answers":False,
            "tls_peer_authenticated":False,"checkpoint_externally_retrieved":False,
            "publisher_independence_authenticated":False,"status":"HOLD",
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
