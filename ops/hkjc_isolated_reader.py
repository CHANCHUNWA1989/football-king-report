"""PR-13: read-only HKJC isolated metadata status gate, never market admission.

Reads only GitHub Contents API latest.json on the fixed isolated research
branch. No old-main fallback, raw odds, provider API calls, bets or EV.
A successful freshness check is not proof of a real tradable quote.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from hkjc_isolated_archive import (
    BRANCH, REPO, LATEST, MAX_BYTES, ArchiveHold, _clock, _parse_unique,
    _sanitized,
)

SCHEMA = "football-king-hkjc-isolated-reader-v1"
MAX_AGE = timedelta(hours=30)  # Daily schedule + short delay, not quote freshness
MAX_FUTURE_SKEW = timedelta(minutes=5)
MAX_HTTP_BYTES = 32_768
GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")


def hold(reason):
    return {
        "schema": SCHEMA, "status": "HOLD",
        "reason": reason,
        "archive_branch": BRANCH,
        "archive_file": LATEST,
        "metadata_recent": False,
        "source_independent": False,
        "licensed_quote_redistribution": False,
        "real_market_quote_verified": False,
        "source_clock_authenticated": False,
        "model_scoring_eligible": False,
        "positive_ev_verified": False,
        "can_execute_bet": False,
        "production_recommendations": "DISABLED",
    }


def _blob_sha1(content):
    return hashlib.sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()


def inspect_latest_record(api_record, *, now):
    """Return metadata freshness assessment with permanent HOLD, never promote.

    The file object is untrusted until its exact name/path, encoded bytes,
    Git blob SHA and strict PR-12 metadata schema are checked.
    """
    if (not isinstance(now, datetime) or now.tzinfo is None
            or now.utcoffset() is None):
        raise ArchiveHold("READER_REQUIRES_UTC_TIME")
    current = now.astimezone(timezone.utc)
    if type(api_record) is not dict:
        raise ArchiveHold("INVALID_LATEST_API_RESPONSE")
    if (api_record.get("type") != "file" or
            api_record.get("name") != "latest.json" or
            api_record.get("path") != LATEST or
            api_record.get("encoding") != "base64" or
            type(api_record.get("content")) is not str or
            type(api_record.get("size")) is not int or
            type(api_record.get("sha")) is not str or
            not GIT_SHA.fullmatch(api_record["sha"])):
        raise ArchiveHold("LATEST_FILE_IDENTITY_MISMATCH")
    try:
        encoded = "".join(api_record["content"].split())
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ArchiveHold("LATEST_BASE64_INVALID") from exc
    if (not 0 < len(raw) <= MAX_BYTES
            or len(raw) != api_record["size"]
            or _blob_sha1(raw) != api_record["sha"]):
        raise ArchiveHold("LATEST_BLOB_INTEGRITY_MISMATCH")
    try:
        doc = _parse_unique(raw.decode("utf-8"))
        canonical = _sanitized(doc)
        captured = _clock(doc["captured_utc"])
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ArchiveHold("LATEST_UNSAFE_METADATA") from exc
    if raw != canonical:
        raise ArchiveHold("NONCANONICAL_ARCHIVE_BYTES")
    age = current - captured
    if age < -MAX_FUTURE_SKEW:
        raise ArchiveHold("ARCHIVE_CAPTURE_IN_FUTURE")
    if age > MAX_AGE:
        raise ArchiveHold("ARCHIVE_METADATA_STALE")
    # Important: even 'RESEARCH_ONLY' means historical observed coverage AT
    # capture, NOT a quote now, and certainly not independent / executable.
    result = hold(
        "RECENT_ISOLATED_METADATA_ONLY_NO_MARKET_ADMISSION"
        if doc["status"] == "RESEARCH_ONLY"
        else "NO_CONFIGURED_OR_QUALIFIED_THIRD_PARTY_MARKET"
    )
    result["metadata_recent"] = True
    result["captured_utc"] = captured.isoformat().replace("+00:00", "Z")
    result["metadata_age_seconds"] = max(0, int(age.total_seconds()))
    result["provider_status_at_capture"] = doc["status"]
    result["requests_at_capture"] = doc["requests_attempted"]
    result["boards_at_capture"] = doc["hkjc_boards_checked"]
    result["market_coverage_at_capture"] = {
        "had": doc["fresh_had_events"],
        "handicap": doc["fresh_handicap_events"],
        "totals": doc["fresh_totals_events"],
        "corners": doc["fresh_corners_events"],
    }
    result["blob_sha1"] = api_record["sha"]
    return result


def read_isolated_latest(*, now=None, token=None, opener=urlopen):
    """No fallback to old main file; no writes or third-party provider access."""
    clock = now if now is not None else datetime.now(timezone.utc)
    url = ("https://api.github.com/repos/" + REPO +
           "/contents/" + LATEST + "?ref=" + quote(BRANCH, safe=""))
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "football-king-isolated-hkjc-read-gate",
    }
    if token:
        if type(token) is not str:
            return hold("INVALID_READ_TOKEN")
        headers["Authorization"] = "Bearer " + token
    request = Request(url, headers=headers, method="GET")
    try:
        with opener(request, timeout=12) as response:
            payload = response.read(MAX_HTTP_BYTES + 1)
        if not 0 < len(payload) <= MAX_HTTP_BYTES:
            return hold("GITHUB_METADATA_RESPONSE_SIZE_INVALID")
        doc = _parse_unique(payload.decode("utf-8"))
        return inspect_latest_record(doc, now=clock)
    except HTTPError as exc:
        if exc.code == 404:
            return hold("ISOLATED_LATEST_NOT_YET_ARCHIVED")
        return hold("GITHUB_READ_PERMISSION_OR_API_UNAVAILABLE")
    except (ArchiveHold, URLError, OSError, ValueError, TypeError,
            UnicodeError, OverflowError) as exc:
        code = str(exc) if type(exc) is ArchiveHold else "ISOLATED_METADATA_READ_FAILED"
        if not re.fullmatch(r"[A-Z0-9_]{3,90}", code):
            code = "ISOLATED_METADATA_READ_FAILED"
        return hold(code)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-auth", action="store_true",
                        help="Request only public, sanitized metadata")
    args = parser.parse_args()
    token = None if args.no_auth else os.environ.get("GH_TOKEN")
    print(json.dumps(read_isolated_latest(token=token), ensure_ascii=False,
                     sort_keys=True))
    # No status can authorize an automated market/production release.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
