"""Firecrawl v2 documented response subset; offline, no requester or secrets."""
import json
from intelligence_x_firecrawl_candidate import intake, MAX_BYTES

ENDPOINT = "https://api.firecrawl.dev/v2/scrape"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError("INVALID_JSON_CONSTANT")


def normalize_response(raw, *, requested_url, reviewed_urls, collected_at,
                       now_utc, http_status):
    """Accept exact captured API response bytes, not publisher bytes.
    
    The caller supplies local collection clock, never an upstream clock.
    This is a conservative documented subset, not an authenticated live capture.
    """
    if type(http_status) is not int or http_status != 200:
        raise ValueError("API_HTTP_NOT_OK")
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("INVALID_RESPONSE_SIZE")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                         parse_constant=_bad_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("INVALID_RESPONSE_JSON") from exc
    if type(obj) is not dict or obj.get("success") is not True or obj.get("error"):
        raise ValueError("API_RESPONSE_NOT_OK")
    data = obj.get("data")
    if type(data) is not dict or data.get("warning"):
        raise ValueError("INVALID_OR_WARNING_DATA")
    md = data.get("markdown")
    if type(md) is not str or not md.strip():
        raise ValueError("MARKDOWN_REQUIRED")
    try:
        md.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("INVALID_MARKDOWN") from exc
    meta = data.get("metadata")
    if type(meta) is not dict or meta.get("error"):
        raise ValueError("INVALID_METADATA")
    # Require both fields: a missing final URL must not silently imply no redirect.
    if meta.get("sourceURL") != requested_url or meta.get("url") != requested_url:
        raise ValueError("SOURCE_URL_MISSING_OR_MISMATCH")
    envelope = {
        "collector": "firecrawl", "requested_url": requested_url,
        "source_url": meta["url"], "status_code": meta.get("statusCode"),
        "collected_at": collected_at,
    }
    result = intake(envelope, raw, reviewed_urls=reviewed_urls, now_utc=now_utc)
    result["payload_kind"] = "firecrawl_v2_api_response_bytes"
    result["upstream_observed_at"] = None
    result["reasons"].append("REDIRECT_HISTORY_UNVERIFIED")
    result["reasons"].append("API_TRANSPORT_UNVERIFIED")
    return result
