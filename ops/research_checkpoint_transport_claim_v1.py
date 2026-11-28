"""Offline composition of checkpoint network safety metadata, never a network attestation."""
from __future__ import annotations
from ops.research_checkpoint_connection_binding_v1 import inspect_checkpoint_connection_binding
from ops.research_checkpoint_tls_metadata_v1 import inspect_checkpoint_tls_metadata
from ops.research_checkpoint_redirect_policy_v1 import inspect_checkpoint_redirect_policy

def inspect_checkpoint_transport_claim(locator:str,dns_answers:list[str],
                                       connection_ip:str,sni_hostname:str,
                                       certificate_hostname:str,
                                       certificate_verified:bool,
                                       response_status:int,
                                       location_header:str|None=None)->dict:
    binding=inspect_checkpoint_connection_binding(locator,dns_answers,connection_ip)
    tls=inspect_checkpoint_tls_metadata(locator,sni_hostname,certificate_hostname,certificate_verified)
    redirect=inspect_checkpoint_redirect_policy(locator,response_status,location_header)
    if not (binding["connection_target_matches_approved_answers"]
            and tls["tls_metadata_consistent"] and redirect["redirect_policy_checked"]):
        raise ValueError("incomplete checkpoint transport policy")
    return {"transport_metadata_policy_checked":True,
            "connection_target_matches_approved_answers":True,
            "tls_metadata_consistent":True,
            "redirect_policy_checked":True,
            "dns_resolution_performed":False,
            "socket_connection_performed":False,
            "tls_handshake_performed":False,
            "tls_peer_authenticated":False,
            "network_request_performed":False,
            "checkpoint_externally_retrieved":False,
            "publisher_identity_authenticated":False,
            "publisher_independence_authenticated":False,
            "status":"HOLD","model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
