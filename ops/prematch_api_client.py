"""Configurable read-only odds API transport with bounded retries.

No credentials or live provider claims are bundled. Caller supplies an HTTPS
endpoint, API key via environment, and provider-specific response mapping.
"""
import hashlib
import json
import os
import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from prematch_raw_archive import archive_response
from prematch_pinned_transport import pinned_https_get
from datetime import datetime, timezone
from prematch_provider_adapter import normalize_provider_snapshot

MAX_BYTES = 1_000_000


def _hold(reason):
    return {"status": "HOLD", "reason": reason,
            "production_recommendations": "DISABLED"}


def fetch_provider_quote(*, url, api_key_env, fixture, model_version,
                         model_probabilities, evaluated_at_utc,
                         provider_id, timeout_seconds=5, max_attempts=3,
                         transport=None, sleeper=None, archive_directory=None,
                         allowed_hosts=None):
    """Fetch a single quote; never promote transport success to source trust.

    Transport returns (status_code, body_bytes, headers). Custom transports
    permit offline fault injection without real HTTP or secrets.
    """
    try:
        parsed = urllib.parse.urlsplit(url) if isinstance(url, str) else None
        port = parsed.port if parsed else None
        host = parsed.hostname if parsed else None
        is_ip_literal = bool(host and _is_ip_literal(host))
    except ValueError:
        return _hold("INVALID_API_CONFIGURATION")
    if (parsed is None or parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or port not in (None, 443)
            or is_ip_literal or host == "localhost" or host.endswith(".localhost")
            or not isinstance(allowed_hosts, (list, tuple, set))
            or host not in allowed_hosts
            or not isinstance(api_key_env, str) or not api_key_env
            or not isinstance(provider_id, str) or not provider_id.strip()
            or type(timeout_seconds) not in (int, float)
            or not 0.1 <= timeout_seconds <= 30
            or type(max_attempts) is not int or not 1 <= max_attempts <= 5):
        return _hold("INVALID_API_CONFIGURATION")
    secret = os.environ.get(api_key_env)
    if not secret:
        return _hold("MISSING_API_CREDENTIAL")
    transport = transport or pinned_https_get
    sleeper = sleeper or time.sleep
    for attempt in range(max_attempts):
        try:
            status, raw, headers = transport(url, secret, timeout_seconds)
            if type(status) is not int or not isinstance(raw, bytes):
                return _hold("INVALID_PROVIDER_RESPONSE")
            if status == 429 or 500 <= status <= 599:
                if attempt + 1 == max_attempts:
                    return _hold("PROVIDER_RATE_LIMITED" if status == 429 else "PROVIDER_UNAVAILABLE")
                retry_after = headers.get("Retry-After") if isinstance(headers, dict) else None
                delay = min(4, 2 ** attempt)
                if isinstance(retry_after, str) and retry_after.isdigit():
                    delay = min(4, max(delay, int(retry_after)))
                sleeper(delay)
                continue
            if status != 200:
                return _hold("PROVIDER_HTTP_ERROR")
            if len(raw) > MAX_BYTES:
                return _hold("OVERSIZED_PROVIDER_RESPONSE")
            document = json.loads(raw)
            if not isinstance(document, dict) or document.get("provider_id") != provider_id:
                return _hold("PROVIDER_IDENTITY_MISMATCH")
            result = normalize_provider_snapshot(
                document, fixture, evaluated_at_utc=evaluated_at_utc,
                model_version=model_version,
                model_probabilities=model_probabilities)
            if result["status"] != "RESEARCH_ONLY":
                return result
            if archive_directory is None:
                return _hold("ARCHIVE_REQUIRED")
            try:
                archive = archive_response(raw, directory=archive_directory)
            except (OSError, ValueError):
                return _hold("ARCHIVE_FAILURE")
            return {**result, "evidence": {
                "archive": archive,
                "response_sha256": hashlib.sha256(raw).hexdigest(),
                "response_byte_count": len(raw),
                "captured_claim_utc": document.get("captured_at_utc"),
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "provider_url_host": parsed.hostname,
                "authentication_verified": False,
                "independent_timestamp_verified": False}}
        except (TimeoutError, socket.timeout, urllib.error.URLError, OSError):
            if attempt + 1 == max_attempts:
                return _hold("PROVIDER_TRANSPORT_FAILURE")
            sleeper(min(4, 2 ** attempt))
        except (ValueError, UnicodeDecodeError, TypeError, RecursionError):
            return _hold("INVALID_PROVIDER_JSON")
    return _hold("PROVIDER_UNAVAILABLE")


def _is_ip_literal(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _https_get(url, secret, timeout_seconds):
    request = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + secret,
                      "Accept": "application/json"}, method="GET")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            return response.status, response.read(MAX_BYTES + 1), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_BYTES + 1), dict(exc.headers)
