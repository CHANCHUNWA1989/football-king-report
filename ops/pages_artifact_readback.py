"""Read-only S0 Pages artifact-to-served-content comparison.

Compares a completed GitHub Pages run's downloaded artifact.tar against the
public site. A byte match is *not* release approval or third-party attestation.
No API token or network write is used by this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

NAMES = ("status.json", "quality.json", "production_gate.json", "market_status.json")
BASE = "https://chanchunwa1989.github.io/football-king-report"
WORKFLOW = "Football King V4.1 iPhone Daily Report"
MAX_ARCHIVE = 100_000_000
MAX_ENTRY = 2_000_000
MAX_TOTAL = 300_000_000
RUN_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("S0_DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def _reject_nonfinite(_):
    raise ValueError("S0_NONFINITE_JSON")


def strict_json(raw: bytes) -> dict:
    if len(raw) > MAX_ENTRY:
        raise ValueError("S0_JSON_OVERSIZE")
    item = json.loads(raw.decode("utf-8"),
                      object_pairs_hook=_unique,
                      parse_constant=_reject_nonfinite)
    if not isinstance(item, dict):
        raise ValueError("S0_DOCUMENT_NOT_OBJECT")
    return item


def _time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("S0_TIMESTAMP_INVALID")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("S0_TIMESTAMP_NAIVE")
    return dt.astimezone(timezone.utc)


def valid_run(run: dict) -> tuple[int, str, datetime, datetime]:
    if (not isinstance(run, dict) or
            run.get("name") != WORKFLOW or
            run.get("head_branch") != "main" or
            run.get("event") not in ("workflow_run", "schedule") or
            type(run.get("id")) is not int or run["id"] < 1 or
            run.get("run_attempt") != 1 or
            run.get("status") != "completed" or
            run.get("conclusion") != "success" or
            not isinstance(run.get("head_sha"), str) or
            not RUN_SHA.fullmatch(run["head_sha"])):
        raise ValueError("S0_UNTRUSTED_PAGES_RUN_METADATA")
    repo = run.get("repository")
    if not isinstance(repo, dict) or repo.get("full_name") != "CHANCHUNWA1989/football-king-report":
        raise ValueError("S0_WRONG_REPOSITORY")
    started, completed = _time(run.get("created_at")), _time(run.get("updated_at"))
    if completed < started or completed - started > timedelta(hours=1):
        raise ValueError("S0_RUN_TIMESPAN_INVALID")
    return run["id"], run["head_sha"], started, completed


def artifact_documents(tar_path: Path) -> dict[str, bytes]:
    p = Path(tar_path)
    if p.is_symlink() or not p.is_file() or not (0 < p.stat().st_size <= MAX_ARCHIVE):
        raise ValueError("S0_PAGES_ARCHIVE_UNSAFE")
    result = {}
    seen = set()
    total = 0
    with tarfile.open(p, mode="r:") as archive:
        for member in archive:
            name = member.name
            if name.startswith("./"):
                name = name[2:]
            if (not name or name.startswith("/") or "\\" in name or
                    any(bit in ("", ".", "..") for bit in name.rstrip("/").split("/"))):
                raise ValueError("S0_PAGES_MEMBER_PATH_UNSAFE")
            if not (member.isfile() or member.isdir()):
                raise ValueError("S0_PAGES_MEMBER_TYPE_UNSAFE")
            if member.size < 0 or member.size > MAX_TOTAL:
                raise ValueError("S0_PAGES_MEMBER_OVERSIZE")
            total += member.size
            if total > MAX_TOTAL:
                raise ValueError("S0_PAGES_ARCHIVE_EXPANSION_LIMIT")
            if name in seen:
                raise ValueError("S0_PAGES_DUPLICATE_MEMBER")
            seen.add(name)
            if name not in NAMES:
                continue
            if not member.isfile() or member.size > MAX_ENTRY:
                raise ValueError("S0_PAGES_REQUIRED_MEMBER_UNSAFE")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("S0_PAGES_REQUIRED_MEMBER_UNREADABLE")
            with stream:
                raw = stream.read(MAX_ENTRY + 1)
            if len(raw) != member.size:
                raise ValueError("S0_PAGES_REQUIRED_MEMBER_SHORT_READ")
            strict_json(raw)
            result[name] = raw
    if set(result) != set(NAMES):
        raise ValueError("S0_PAGES_REQUIRED_FILES_MISSING")
    return result


def get_public(name: str) -> bytes:
    if name not in NAMES:
        raise ValueError("S0_PUBLIC_PATH_NOT_ALLOWED")
    url = BASE + "/" + name
    req = urllib.request.Request(url, headers={
        "Cache-Control": "no-cache", "Accept": "application/json",
        "User-Agent": "football-king-s0-pages-readback/1"})
    with urllib.request.urlopen(req, timeout=12) as reply:
        if reply.status != 200 or reply.geturl() != url:
            raise ValueError("S0_PUBLIC_STATUS_OR_REDIRECT_INVALID")
        size = reply.headers.get("Content-Length")
        if size is not None and int(size) > MAX_ENTRY:
            raise ValueError("S0_PUBLIC_RESPONSE_TOO_LARGE")
        body = reply.read(MAX_ENTRY + 1)
    if len(body) > MAX_ENTRY:
        raise ValueError("S0_PUBLIC_RESPONSE_TOO_LARGE")
    strict_json(body)
    return body


def _safety(documents: dict[str, bytes], *, started: datetime,
            completed: datetime) -> dict:
    parsed = {key: strict_json(value) for key, value in documents.items()}
    if any(doc.get("production_recommendations") != "DISABLED"
           for doc in parsed.values()):
        raise ValueError("S0_PRODUCTION_NOT_DISABLED")
    if (parsed["status.json"].get("status") != "RESEARCH_ONLY" or
            parsed["quality.json"].get("status") != "RESEARCH_ONLY" or
            parsed["production_gate.json"].get("status") != "HOLD" or
            parsed["production_gate.json"].get("authenticated_forward_samples") != 0):
        raise ValueError("S0_RELEASE_GATE_WEAKENED")
    status_at = parsed["status.json"].get("checked_utc")
    quality_at = parsed["quality.json"].get("checked_utc")
    if status_at != quality_at:
        raise ValueError("S0_STATUS_QUALITY_CLOCK_MISMATCH")
    checked = _time(status_at)
    if not started - timedelta(minutes=5) <= checked <= completed + timedelta(minutes=5):
        raise ValueError("S0_PAGES_CLOCK_OUTSIDE_RUN")
    return {"checked_utc": checked.isoformat(),
            "public_fixture_count": parsed["quality.json"].get("public_matches"),
            "authenticated_forward_samples": 0,
            "production_recommendations": "DISABLED"}


def compare(tar_path: Path, run: dict, *, fetch=get_public) -> dict:
    """Always returns an explicit fail-closed receipt; never a release GO."""
    receipt = {
        "schema": "football-king-s0-pages-byte-readback-v1",
        "status": "HOLD_S0_EVIDENCE_INCOMPLETE",
        "all_required_public_files_byte_matched": False,
        "artifact_deployed_content_link_corroborated": False,
        "deployment_commit_sha_independently_attested": False,
        "source_identity_or_time_attested": False,
        "independent_reviewer_approved": False,
        "production_recommendations": "DISABLED",
        "verified_positive_ev": False,
        "release_authorized": False,
        "matches": {},
    }
    try:
        run_id, head, started, completed = valid_run(run)
        receipt["run_id"] = run_id
        receipt["source_head_sha"] = head
        artifact = artifact_documents(tar_path)
        _safety(artifact, started=started, completed=completed)
        live = {}
        for name in NAMES:
            live[name] = fetch(name)
            strict_json(live[name])
            receipt["matches"][name] = {
                "artifact_sha256": hashlib.sha256(artifact[name]).hexdigest(),
                "public_sha256": hashlib.sha256(live[name]).hexdigest(),
                "byte_match": artifact[name] == live[name],
            }
        _safety(live, started=started, completed=completed)
        if not all(item["byte_match"] for item in receipt["matches"].values()):
            raise ValueError("S0_PUBLIC_SITE_DIFFERS_FROM_PAGES_ARTIFACT")
        receipt["status"] = "CONTENT_MATCHED_NOT_RELEASE_AUTHORIZATION"
        receipt["all_required_public_files_byte_matched"] = True
        receipt["artifact_deployed_content_link_corroborated"] = True
    except (OSError, ValueError, KeyError, TypeError, UnicodeError,
            json.JSONDecodeError, tarfile.TarError) as exc:
        receipt["status"] = "HOLD_S0_EVIDENCE_INCOMPLETE"
        receipt["reason"] = str(exc)[:160]
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-content-match", action="store_true")
    args = parser.parse_args()
    try:
        run = strict_json(Path(args.run).read_bytes())
        result = compare(Path(args.artifact), run)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        result = {"schema": "football-king-s0-pages-byte-readback-v1",
                  "status": "HOLD_S0_EVIDENCE_INCOMPLETE",
                  "reason": str(exc)[:160],
                  "release_authorized": False,
                  "production_recommendations": "DISABLED",
                  "verified_positive_ev": False}
    out = Path(args.output)
    out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if args.require_content_match and result["status"] != "CONTENT_MATCHED_NOT_RELEASE_AUTHORIZATION":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
