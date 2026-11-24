"""Offline Firecrawl candidate envelope intake. No network or model promotion."""
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

MAX_BYTES = 512 * 1024
MAX_AGE_SECONDS = 900
_CLOCK_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)
_INTERNAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".home.arpa", ".onion", ".invalid", ".test")


def _clock(value):
    if not isinstance(value, str):
        raise ValueError("TIMESTAMP_REQUIRED")
    if len(value) > 40 or not _CLOCK_PATTERN.fullmatch(value) or value.endswith("-00:00"):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("TIMEZONE_REQUIRED")
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc


def _url(value):
    if not isinstance(value, str) or not value.isascii() or len(value) > 2048:
        raise ValueError("INVALID_URL")
    if not re.fullmatch(r"https://[a-z0-9.-]+/[A-Za-z0-9._~/-]*", value):
        raise ValueError("INVALID_URL")
    p = urlsplit(value)
    if (not p.hostname or len(p.hostname) > 253 or "." not in p.hostname or
            p.hostname.endswith(_INTERNAL_SUFFIXES) or
            any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in p.hostname.split(".")) or
            not re.fullmatch(r"[a-z][a-z0-9-]*", p.hostname.split(".")[-1]) or
            any(x in (".", "..") for x in p.path.split("/")) or
            "//" in p.path):
        raise ValueError("INVALID_URL")
    return value


def intake(envelope, body, *, reviewed_urls, now_utc, max_age_seconds=900):
    """Hash an already-loaded response; reviewed URLs are not permission grants.

    Input is an internal normalized envelope, not a Firecrawl SDK response.
    Body is the exact supplied bytes, not evidence of publisher originality.
    """
    if not isinstance(envelope, dict) or envelope.get("collector") != "firecrawl":
        raise ValueError("INVALID_ENVELOPE")
    if not isinstance(reviewed_urls, (set, frozenset)) or not reviewed_urls:
        raise ValueError("REVIEWED_URLS_REQUIRED")
    allowed = {_url(v) for v in reviewed_urls}
    requested = _url(envelope.get("requested_url"))
    returned = _url(envelope.get("source_url"))
    if requested != returned or requested not in allowed:
        raise ValueError("URL_NOT_REVIEWED_OR_CHANGED")
    if type(envelope.get("status_code")) is not int or envelope["status_code"] != 200:
        raise ValueError("HTTP_STATUS_NOT_OK")
    if type(body) is not bytes or not 0 < len(body) <= MAX_BYTES:
        raise ValueError("INVALID_BODY_SIZE")
    if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= MAX_AGE_SECONDS:
        raise ValueError("INVALID_MAX_AGE")
    now = _clock(now_utc)
    collected = _clock(envelope.get("collected_at"))
    if not 0 <= (now - collected).total_seconds() <= max_age_seconds:
        raise ValueError("COLLECTION_CLOCK_OUT_OF_RANGE")
    upstream = envelope.get("upstream_observed_at")
    if upstream is not None:
        observed = _clock(upstream)
        if not 0 <= (collected - observed).total_seconds() or (now - observed).total_seconds() > max_age_seconds:
            raise ValueError("UPSTREAM_CLOCK_OUT_OF_RANGE")
    return {
        "schema": "intelligence-x-firecrawl-candidate-v1",
        "collector": "firecrawl",
        "source_url": returned,
        "collected_at": collected.isoformat(),
        "upstream_observed_at": None if upstream is None else observed.isoformat(),
        "payload_sha256": hashlib.sha256(body).hexdigest(),
        "payload_bytes": len(body),
        "status": "HOLD",
        "source_authorized": False,
        "independently_verified": False,
        "eligible_for_model_scoring": False,
        "production_recommendations": "DISABLED",
        "reasons": ["RIGHTS_UNVERIFIED", "PUBLISHER_ORIGIN_UNVERIFIED",
                    "UPSTREAM_CLOCK_UNVERIFIED" if upstream is not None else "UPSTREAM_CLOCK_MISSING",
                    "NO_INDEPENDENT_CORROBORATION"],
    }
