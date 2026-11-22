"""Offline, fail-closed quarantine intake for manually exported Agent Reach research.

This module does not import Agent Reach, connect to networks, authenticate any
source, link event identities, run forecasts, or output the untrusted text.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

MAX_INPUT_BYTES = 1_000_000
MAX_RECORDS = 100
MAX_TEXT_CHARS = 65_536
CHANNELS = frozenset({"web", "github", "youtube", "rss"})
SPORTS = frozenset({"football", "horse_racing"})
SOURCE_TYPES = frozenset({"official_claimed", "reporting", "community"})
ID_RE = re.compile(r"[A-Za-z0-9:._-]{1,96}\Z")
HOST_RE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")


class Rejected(ValueError):
    """An item cannot enter the quarantine ledger."""


def utc(value: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 40:
        raise Rejected("INVALID_TIMESTAMP")
    try:
        value = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise Rejected("INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Rejected("NAIVE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def https_public_url(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise Rejected("INVALID_URL")
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower()
        port = url.port
    except ValueError as exc:
        raise Rejected("INVALID_URL") from exc
    if (url.scheme != "https" or url.username is not None or
            url.password is not None or port not in (None, 443) or
            url.query or url.fragment or not HOST_RE.fullmatch(host) or
            host.endswith((".internal", ".local", ".localhost", ".test", ".invalid", ".example"))):
        raise Rejected("UNSAFE_URL")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise Rejected("IP_LITERAL_URL")
    return value, host


def intake(payload: object, *, now_utc: str) -> dict:
    """Validate envelopes only. Never claim authenticity or model eligibility."""
    now = utc(now_utc)
    if not isinstance(payload, dict) or type(payload.get("records")) is not list:
        raise Rejected("INVALID_ENVELOPE")
    records = payload["records"]
    if len(records) > MAX_RECORDS:
        raise Rejected("TOO_MANY_RECORDS")
    out = []
    seen = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise Rejected(f"INVALID_RECORD_{index}")
        sport, channel, typ = (record.get("sport"), record.get("channel"),
                               record.get("source_type"))
        if (not isinstance(sport, str) or sport not in SPORTS or
                not isinstance(channel, str) or channel not in CHANNELS or
                not isinstance(typ, str) or typ not in SOURCE_TYPES):
            raise Rejected(f"UNKNOWN_CLASSIFICATION_{index}")
        source_url, host = https_public_url(record.get("source_url"))
        event_id = record.get("event_id")
        if event_id is not None and (not isinstance(event_id, str) or
                                     not ID_RE.fullmatch(event_id)):
            raise Rejected(f"INVALID_EVENT_ID_{index}")
        body = record.get("content")
        if not isinstance(body, str) or not 1 <= len(body) <= MAX_TEXT_CHARS:
            raise Rejected(f"INVALID_CONTENT_{index}")
        captured = utc(record.get("captured_utc"))
        if captured > now or captured < now - timedelta(days=30):
            raise Rejected(f"CAPTURE_OUT_OF_WINDOW_{index}")
        published_raw = record.get("published_utc")
        published = utc(published_raw) if published_raw is not None else None
        if published is not None and published > captured:
            raise Rejected(f"PUBLISHED_AFTER_CAPTURE_{index}")
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        key = (sport, channel, source_url, event_id, published)
        if key in seen:
            if seen[key] != digest:
                raise Rejected(f"CONFLICTING_DUPLICATE_{index}")
            continue
        seen[key] = digest
        out.append({
            "sport": sport,
            "channel": channel,
            "source_type_claimed": typ,
            "source_url": source_url,
            "source_domain": host,
            "event_id_unverified": event_id,
            "published_utc_unverified": published.isoformat().replace("+00:00", "Z") if published else None,
            "captured_utc_unverified": captured.isoformat().replace("+00:00", "Z"),
            "content_sha256_local_only": digest,
            "status": "QUARANTINE",
            "reason": "EXTERNAL_ORIGIN_AND_TIME_NOT_AUTHENTICATED",
            "source_authorized": False,
            "identity_verified": False,
            "time_attested": False,
            "eligible_for_model": False,
            "verified_market_odds": False,
            "verified_positive_ev": None,
        })
    return {
        "schema": "agent-reach-research-quarantine-v1",
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "agent_reach_executed": False,
        "network_requests": 0,
        "raw_content_retained": False,
        "record_count": len(out),
        "records": out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--now-utc", required=True, help="Unattested processing clock; never source evidence")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("input and output must differ")
    try:
        if args.input.stat().st_size > MAX_INPUT_BYTES:
            raise Rejected("INPUT_TOO_LARGE")
        result = intake(json.loads(args.input.read_text(encoding="utf-8")), now_utc=args.now_utc)
    except (Rejected, OSError, UnicodeError, json.JSONDecodeError) as exc:
        parser.error(f"QUARANTINE_REJECTED: {type(exc).__name__}")
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
