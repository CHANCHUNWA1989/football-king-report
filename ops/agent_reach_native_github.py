"""Fail-closed import of Agent Reach v1.6 native JSON for one public GitHub repo.

This is NOT a downloader or a credentialed client. Input must be supplied as
a file after a separate, approved, anonymous Agent Reach CLI execution.
Never promote records to model features or treat metadata as attestation.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from agent_reach_quarantine import Rejected, intake

MAX_NATIVE_BYTES = 200_000
_REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})?/[A-Za-z0-9._-]{1,100}\Z")


def canonical_repo(value: object) -> str:
    if not isinstance(value, str) or not _REPO.fullmatch(value):
        raise Rejected("INVALID_PINNED_REPOSITORY")
    owner, repo = value.split("/", 1)
    if repo in (".", "..") or repo.startswith("."):
        raise Rejected("INVALID_PINNED_REPOSITORY")
    return f"{owner}/{repo}"


def public_repo_url(value: object, expected_repo: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 250:
        raise Rejected("UNSAFE_GITHUB_URL")
    try:
        u = urlsplit(value)
        port = u.port
    except ValueError as exc:
        raise Rejected("UNSAFE_GITHUB_URL") from exc
    if (u.scheme != "https" or u.hostname != "github.com" or port is not None or
            u.username is not None or u.password is not None or u.query or u.fragment or
            u.path.rstrip("/").lower() != f"/{expected_repo}".lower()):
        raise Rejected("UNEXPECTED_GITHUB_SOURCE")
    # The returned URL is canonicalized, avoiding redirects and query-string credentials.
    return f"https://github.com/{expected_repo}"


def public_read_command(repo: str) -> tuple[str, ...]:
    """Human-readable explicit command; this module never executes it."""
    repo = canonical_repo(repo)
    return ("agent-reach", "github", "read", repo, "--backend", "github-api", "--timeout", "15")


def convert_native(envelope: object, *, repo: str, captured_utc: str,
                   now_utc: str) -> dict:
    repo = canonical_repo(repo)
    if not isinstance(envelope, dict):
        raise Rejected("INVALID_AGENT_REACH_ENVELOPE")
    if (type(envelope.get("schema_version")) is not int or
            envelope["schema_version"] != 1 or envelope.get("ok") is not True or
            envelope.get("channel") != "github" or envelope.get("action") != "read" or
            envelope.get("backend") != "github-api" or
            envelope.get("error") is not None):
        raise Rejected("UNVERIFIED_AGENT_REACH_ENVELOPE")
    items = envelope.get("items")
    if not isinstance(items, list) or len(items) != 1:
        raise Rejected("UNEXPECTED_RESULT_COUNT")
    item = items[0]
    if not isinstance(item, dict):
        raise Rejected("INVALID_AGENT_REACH_ITEM")
    url = public_repo_url(item.get("url"), repo)
    title = item.get("title")
    if not isinstance(title, str) or title.casefold() != repo.casefold():
        raise Rejected("REPOSITORY_IDENTITY_MISMATCH")
    body = item.get("text")
    if not isinstance(body, str) or not body.strip():
        raise Rejected("NO_READABLE_BODY")
    # item.published_at is usually the repository CREATION date; it is not the
    # README or Issue content publication timestamp. NEVER copy it across.
    result = intake({"records": [{
        "sport": "football",
        "channel": "github",
        "source_type": "community",
        "source_url": url,
        "event_id": None,
        "published_utc": None,
        "captured_utc": captured_utc,
        "content": body,
    }]}, now_utc=now_utc)
    result.update({
        "import_mode": "NATIVE_ENVELOPE_ONLY",
        "agent_reach_native_schema_version": 1,
        "agent_reach_execution_independently_verified": False,
        "auth_or_source_time_verified": False,
        "upstream_backend_claimed": "github-api",
    })
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True, help="Explicitly chosen public owner/repository")
    p.add_argument("--native-json", required=True, type=Path, help="Local untrusted CLI JSON output")
    p.add_argument("--output", required=True, type=Path, help="Local quarantined metadata only")
    p.add_argument("--captured-utc", required=True, help="Caller-supplied, not attested")
    p.add_argument("--now-utc", required=True, help="Caller-supplied, not attested")
    args = p.parse_args()
    if args.native_json.resolve() == args.output.resolve():
        p.error("input and output must differ")
    try:
        if args.native_json.stat().st_size > MAX_NATIVE_BYTES:
            raise Rejected("NATIVE_OUTPUT_TOO_LARGE")
        source = json.loads(args.native_json.read_text(encoding="utf-8"))
        result = convert_native(source, repo=args.repo,
                                captured_utc=args.captured_utc,
                                now_utc=args.now_utc)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (Rejected, OSError, UnicodeError, json.JSONDecodeError):
        p.error("QUARANTINE_HOLD: invalid, mismatched, or unauthorized native evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
