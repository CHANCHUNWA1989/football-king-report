"""Conservative offline URL policy; does not perform network retrieval."""
from __future__ import annotations
import ipaddress
from urllib.parse import urlsplit

def inspect_checkpoint_locator(locator:str)->dict:
    if type(locator) is not str or not locator or len(locator)>2048:
        raise ValueError("invalid checkpoint locator")
    if any(ord(c)<33 or ord(c)==127 for c in locator):
        raise ValueError("control or whitespace in locator")
    try:
        parsed=urlsplit(locator)
        port=parsed.port
    except ValueError as exc:
        raise ValueError("invalid locator authority") from exc
    if parsed.scheme!="https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("HTTPS hostname without credentials required")
    if parsed.fragment or port not in (None,443):
        raise ValueError("fragment or nonstandard port rejected")
    host=parsed.hostname.rstrip(".").lower()
    if not host or host=="localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("local host rejected")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        if "." not in host or any(not label or len(label)>63 for label in host.split(".")):
            raise ValueError("public DNS hostname required")
    else:
        raise ValueError("IP literal rejected; pinned public DNS name required")
    return {"locator_policy_checked":True,"network_retrieval_performed":False,
            "dns_resolution_verified":False,"tls_peer_authenticated":False,
            "publisher_independence_authenticated":False,"status":"HOLD",
            "model_promotion_allowed":False}
