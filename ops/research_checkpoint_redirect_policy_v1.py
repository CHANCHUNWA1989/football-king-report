"""Research-only fail-closed redirect policy; never follows HTTP redirects."""
from __future__ import annotations
from urllib.parse import urlsplit
from ops.research_checkpoint_locator_policy_v1 import inspect_checkpoint_locator

def inspect_checkpoint_redirect_policy(original_locator:str,
                                       response_status:int,
                                       location_header:str|None=None)->dict:
    inspect_checkpoint_locator(original_locator)
    if type(response_status) is not int or not 100<=response_status<=599:
        raise ValueError("valid HTTP response status required")
    if 300<=response_status<=399:
        raise ValueError("checkpoint redirects forbidden, including relative redirects")
    if response_status!=200:
        raise ValueError("checkpoint response must be HTTP 200")
    if location_header is not None:
        raise ValueError("unexpected Location header rejected")
    return {"redirect_policy_checked":True,
            "redirects_followed":False,
            "network_request_performed":False,
            "tls_peer_authenticated":False,
            "checkpoint_externally_retrieved":False,
            "status":"HOLD","model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
