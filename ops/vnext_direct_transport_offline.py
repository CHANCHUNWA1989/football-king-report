"""Offline transport policy rehearsal. No provider credentials or network I/O.

Builds a reference urllib opener but never opens a connection. Explicit proxy
and trust-store environment overrides fail closed. No claim about runner DNS,
system trust roots, transparent proxies, or actual TLS peer authentication.
"""
import json
import ssl
from urllib.request import (Request, build_opener, ProxyHandler, HTTPSHandler,
                            HTTPRedirectHandler)
from vnext_api_football_live_probe import URL, summarize

MAX_BYTES = 1200000
SYNTHETIC_KEY = "offline-fixture-not-a-real-key"
BLOCKED_ENV = frozenset({"http_proxy", "https_proxy", "all_proxy", "no_proxy",
                         "ftp_proxy", "ssl_cert_file", "ssl_cert_dir",
                         "requests_ca_bundle", "curl_ca_bundle"})


class DenyRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("REDIRECT_REJECTED")


def build_reference_opener(env):
    """Construct only, never perform I/O. env is declared research metadata."""
    if any(str(k).lower() in BLOCKED_ENV for k in env):
        raise ValueError("UNAPPROVED_ENVIRONMENT")
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise ValueError("UNSAFE_TLS_CONTEXT")
    return build_opener(ProxyHandler({}), HTTPSHandler(context=context), DenyRedirect())


def unique_object(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError("DUPLICATE_JSON_KEY")
        obj[k] = v
    return obj


def reject_constant(value):
    raise ValueError("NONFINITE_JSON")


def report(reason, rows=0):
    return {"status": "HOLD", "reason": reason, "synthetic_rows": rows,
            "real_requests": 0, "real_request_authorized": False,
            "production_recommendations": "DISABLED"}


def rehearse(*, env, response_url, status, content_type, body):
    """Evaluate supplied synthetic response; no callback or network capability."""
    try:
        build_reference_opener(env)
        req = Request(URL, headers={"x-apisports-key": SYNTHETIC_KEY,
                                    "Accept": "application/json"}, method="GET")
        if response_url != req.full_url:
            return report("DESTINATION_MISMATCH")
        if type(status) is not int or status != 200:
            return report("HTTP_STATUS_REJECTED")
        if type(content_type) is not str or content_type.split(";", 1)[0].strip().lower() != "application/json":
            return report("CONTENT_TYPE_REJECTED")
        if type(body) is not bytes or not 0 < len(body) <= MAX_BYTES:
            return report("BODY_SIZE_OR_TYPE_REJECTED")
        data = json.loads(body.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
        _, rows = summarize(data)
        return report("SYNTHETIC_RESPONSE_ONLY", rows)
    except (ValueError, TypeError, AttributeError, OSError, OverflowError, RecursionError):
        return report("POLICY_OR_SCHEMA_REJECTED")
