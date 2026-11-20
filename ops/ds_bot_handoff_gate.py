"""Fail-closed, offline boundary for *untrusted* DS Bot research notes.

This module is not a DS Bot runtime or a data-source authenticator. It never
imports DeepSeek Harness, accesses the network, executes model content, or
updates production files. Its only output is safe metadata marked HOLD.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "football-king-dsbot-handoff-v1"
OUTPUT_SCHEMA = "football-king-dsbot-gate-v1"
MAX_BYTES = 65536
MAX_NOTE_LENGTH = 1600
MAX_AGE = timedelta(hours=24)
ROLES = frozenset(("fixture_audit", "market_audit", "model_challenge", "review_notes"))
TOP_KEYS = frozenset((
    "schema", "origin", "run_id", "generated_at_utc", "as_of_utc",
    "status", "production_recommendations", "observations",
))
ROW_KEYS = frozenset(("role", "note", "references"))
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
UTC_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class HandoffRejected(ValueError):
    """Untrusted input failed the strict, non-promoting handoff contract."""


def _fail(reason: str) -> None:
    raise HandoffRejected(reason)


def _timestamp(raw: object) -> datetime:
    if not isinstance(raw, str) or not UTC_STAMP.fullmatch(raw):
        _fail("UTC_TIMESTAMP_REQUIRED")
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _fail("INVALID_TIMESTAMP")


def _ref_ok(raw: object) -> bool:
    if not isinstance(raw, str) or len(raw) > 512 or len(raw) < 10:
        return False
    if any(ord(c) < 33 or ord(c) > 126 for c in raw):
        return False
    try:
        u = urlsplit(raw)
        return bool(u.scheme == "https" and u.hostname and u.username is None
                    and u.password is None and u.port in (None, 443)
                    and not u.query and not u.fragment)
    except ValueError:
        return False


def validate_handoff(payload: object, *, now: datetime | None = None) -> dict:
    """Validate DS Bot-authored JSON; output only HOLD metadata, never note text."""
    if not isinstance(payload, dict) or set(payload) != TOP_KEYS:
        _fail("UNEXPECTED_HANDOFF_FIELDS")
    if payload["schema"] != SCHEMA or payload["origin"] != "ds-bot":
        _fail("UNSUPPORTED_ORIGIN_OR_SCHEMA")
    if not isinstance(payload["run_id"], str) or not RUN_ID.fullmatch(payload["run_id"]):
        _fail("INVALID_RUN_ID")
    if (payload["status"] != "RESEARCH_ONLY"
            or payload["production_recommendations"] != "DISABLED"):
        _fail("UNSAFE_STATUS")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current = current.astimezone(timezone.utc)
    generated = _timestamp(payload["generated_at_utc"])
    as_of = _timestamp(payload["as_of_utc"])
    if generated > current + timedelta(minutes=5) or as_of > generated:
        _fail("FUTURE_OR_LOOKAHEAD_TIMESTAMP")
    if current - generated > MAX_AGE:
        _fail("STALE_HANDOFF")
    rows = payload["observations"]
    if not isinstance(rows, list) or not (1 <= len(rows) <= len(ROLES)):
        _fail("INVALID_OBSERVATION_COUNT")
    seen = set()
    ref_count = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_KEYS:
            _fail("UNEXPECTED_OBSERVATION_FIELDS")
        role = row["role"]
        if not isinstance(role, str) or role not in ROLES or role in seen:
            _fail("INVALID_OR_DUPLICATE_ROLE")
        seen.add(role)
        note = row["note"]
        if (not isinstance(note, str) or not note.strip()
                or len(note) > MAX_NOTE_LENGTH or "\x00" in note):
            _fail("INVALID_NOTE")
        refs = row["references"]
        if (not isinstance(refs, list) or len(refs) > 4
                or not all(isinstance(url, str) for url in refs)):
            _fail("INVALID_REFERENCES")
        if len(refs) != len(set(refs)):
            _fail("INVALID_REFERENCES")
        if not all(_ref_ok(url) for url in refs):
            _fail("INVALID_REFERENCE_URL")
        ref_count += len(refs)
    # Content hash is repeatable, NOT proof of origin or timestamp.
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "research_only": True,
        "upstream_identity_authenticated": False,
        "independent_source_authentication": False,
        "independent_human_review": False,
        "authenticated_forward_samples": 0,
        "verified_positive_ev": False,
        "eligible_for_prediction_or_betting": False,
        "reason": "UNTRUSTED_DSBOT_NOTES_ONLY",
        "observation_count": len(rows),
        "reference_count_unverified": ref_count,
        "payload_sha256_unattested": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _reject_duplicate_keys(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def inspect_file(path: Path, *, now: datetime | None = None) -> dict:
    """Opt-in read of a bounded local JSON file; do not print untrusted content."""
    if path.is_symlink():
        _fail("SYMLINK_INPUT_DISALLOWED")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
        _fail("INVALID_FILE_SIZE_OR_TYPE")
    content = path.read_bytes()
    if len(content) > MAX_BYTES:
        _fail("OVERSIZED_HANDOFF")
    try:
        payload = json.loads(content, object_pairs_hook=_reject_duplicate_keys,
                             parse_constant=lambda _: _fail("INVALID_JSON_NUMBER"))
    except HandoffRejected:
        raise
    except (ValueError, UnicodeDecodeError):
        _fail("INVALID_JSON")
    return validate_handoff(payload, now=now)


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline DS Bot research handoff gate (HOLD only)")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inspect_file(args.input)
    except (HandoffRejected, OSError) as exc:
        # Error reasons are controlled labels; no private file data is printed.
        reason = str(exc) if isinstance(exc, HandoffRejected) else "INPUT_UNAVAILABLE"
        print(json.dumps({"schema": OUTPUT_SCHEMA, "status": "HOLD",
                          "production_recommendations": "DISABLED", "reason": reason}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
