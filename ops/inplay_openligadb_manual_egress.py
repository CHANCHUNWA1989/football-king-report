"""Fail-closed *procedural* preflight for manual OpenLigaDB research HTTP.

This is an in-process check, NOT an OS firewall, proxy isolation certificate,
independent network attestation, external timestamp, permission grant or
production deployment approval. The only sanctioned live path still requires
PR546's changed-token, native-ID and shared-host pacing gates.

Default deny: no opt-in, hosted CI, proxy/TLS override, elevated UID or
unsupported runtime. Return only fixed safe reasons, never environment values
or private data. Injected fake HTTP getters in unit tests are exempt because
they do not invoke the true transport.
"""
import os
from collections.abc import Mapping

SCHEMA="football-king-openligadb-manual-egress-preflight-v1"
ACK_KEY="FOOTBALL_KING_OPENLIGA_MANUAL_EGRESS"
ACK_VALUE="ONE_SHOT_RESEARCH_V1"

RUNNER_KEYS=frozenset((
    "CI","GITHUB_ACTIONS","GITHUB_RUN_ID","RUNNER_OS",
    "ACTIONS_RUNTIME_TOKEN","GITHUB_TOKEN",
))
PROXY_TLS_KEYS=frozenset((
    "HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","FTP_PROXY","NO_PROXY",
    "SSL_CERT_FILE","SSL_CERT_DIR","SSLKEYLOGFILE","PYTHONHTTPSVERIFY",
    "REQUESTS_CA_BUNDLE","CURL_CA_BUNDLE","GIT_SSL_NO_VERIFY",
))


class ManualEgressDenied(ValueError):
    """Public-safe fixed denial reason; do not expose environment values."""


def _report(reason="NOT_READY_FOR_MANUAL_EGRESS"):
    return {
        "schema":SCHEMA,
        "status":"HOLD",
        "reason":reason,
        "manual_research_http_preflight_passed":False,
        "host_firewall_isolation_verified":False,
        "cross_host_rate_control_verified":False,
        "production_http_isolation_certified":False,
        "source_authenticated":False,
        "provider_identity_verified":False,
        "externally_witnessed":False,
        "eligible_for_model_input":False,
        "positive_ev_verified":False,
        "certified_forward_samples":0,
        "production_recommendations":"DISABLED",
        "recommendation":None,
        "roi":None,
    }


def inspect_manual_egress(environ=None):
    """Inspect current process configuration without reading secret values.

    Pass an explicit mapping for synthetic tests. False-positive denials are
    preferred over implicitly issuing a real public API request.
    """
    env=os.environ if environ is None else environ
    if (not isinstance(env,Mapping)
            or any(type(k) is not str or type(v) is not str
                   for k,v in env.items())):
        return _report("INVALID_PROCESS_ENVIRONMENT")
    names={name.upper() for name in env}
    if names & RUNNER_KEYS:
        return _report("CI_OR_HOSTED_RUNNER_FORBIDDEN")
    if names & PROXY_TLS_KEYS:
        return _report("PROXY_OR_TLS_OVERRIDE_FORBIDDEN")
    if env.get(ACK_KEY)!=ACK_VALUE:
        return _report("MISSING_MANUAL_EGRESS_ACKNOWLEDGEMENT")
    if os.name!="posix" or not hasattr(os,"geteuid"):
        return _report("UNSUPPORTED_MANUAL_EGRESS_PLATFORM")
    try:
        uid=os.geteuid()
    except (OSError,TypeError):
        return _report("UNSUPPORTED_MANUAL_EGRESS_PLATFORM")
    if uid==0:
        return _report("PRIVILEGED_EXECUTION_FORBIDDEN")
    return {
        **_report("LOCAL_MANUAL_EGRESS_CHECK_ONLY"),
        "status":"RESEARCH_ONLY",
        "manual_research_http_preflight_passed":True,
    }


def require_manual_egress(environ=None):
    """Require preflight at the *real* HTTP boundary. Never echo env values."""
    result=inspect_manual_egress(environ)
    if result["status"]!="RESEARCH_ONLY":
        raise ManualEgressDenied(result["reason"])
    return result
