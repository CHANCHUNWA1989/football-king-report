"""Offline TLS identity policy. Supplied metadata is not a verified TLS handshake."""
from __future__ import annotations
from urllib.parse import urlsplit
from ops.research_checkpoint_locator_policy_v1 import inspect_checkpoint_locator

def inspect_checkpoint_tls_metadata(locator:str, sni_hostname:str,
                                    certificate_hostname:str,
                                    certificate_verified:bool)->dict:
    inspect_checkpoint_locator(locator)
    host=urlsplit(locator).hostname
    if type(sni_hostname) is not str or type(certificate_hostname) is not str:
        raise ValueError("TLS hostnames required")
    if sni_hostname!=host or certificate_hostname!=host:
        raise ValueError("TLS hostname does not match checkpoint origin")
    if certificate_verified is not True:
        raise ValueError("verified certificate metadata required")
    return {"tls_metadata_consistent":True,
            "tls_handshake_performed":False,
            "tls_peer_authenticated":False,
            "certificate_chain_independently_verified":False,
            "network_request_performed":False,
            "publisher_identity_authenticated":False,
            "status":"HOLD","model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
