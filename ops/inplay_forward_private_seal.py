"""Opt-in, private, on-run in-play evidence-candidate seal (never a trust root).

This sidecar consumes user/operator-supplied bytes; it does not fetch any feeds.
A local clock and digest cannot prove source authenticity or prove that a
candidate existed at an earlier time. Do not commit raw subjects to GitHub.
Requires the separate inplay_hkjc_evidence_binding audit, stacked PR #544.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile
from datetime import datetime, timezone

from inplay_hkjc_evidence_binding import audit as audit_claims

SCHEMA = "football-king-inplay-private-candidate-seal-v1"
SCORES = ("score_primary", "score_secondary")
MAXIMUMS = {
    "fixture_seal.json": 128_000,
    "score_primary.raw": 1_000_000,
    "score_secondary.raw": 1_000_000,
    "quote.raw": 1_000_000,
    "screenshot.raw": 15_000_000,
}
MAX_ARCHIVE_BYTES = 19_000_000


class CandidateSealError(ValueError):
    """Return only a fixed rejection code; never reveal private raw bytes."""


def _reject(condition, reason):
    if not condition:
        raise CandidateSealError(reason)


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique_pairs(pairs):
    result = {}
    for key, val in pairs:
        _reject(key not in result, "DUPLICATE_FIXTURE_SEAL_FIELD")
        result[key] = val
    return result


def _no_nonfinite(_):
    raise CandidateSealError("NONFINITE_FIXTURE_SEAL")


def _validate_seal(fixture, raw):
    _reject(type(raw) is bytes and 0 < len(raw) <= MAXIMUMS["fixture_seal.json"],
            "INVALID_FIXTURE_SEAL_BYTES")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                             parse_constant=_no_nonfinite)
        _reject(type(payload) is dict and set(payload) == {"fixture", "provenance_notice"}
                and payload["provenance_notice"] == "SELF_DECLARED_NOT_ATTESTED"
                and _canonical_json(payload["fixture"]) == _canonical_json(fixture),
                "FIXTURE_SEAL_NOT_BOUND")
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        raise CandidateSealError("INVALID_OR_MISMATCHED_FIXTURE_SEAL") from None


def _read_now(now):
    if now is None:
        return datetime.now(timezone.utc)
    _reject(isinstance(now, datetime) and now.tzinfo is not None
            and now.utcoffset() is not None,
            "INVALID_TEST_CLOCK")
    return now.astimezone(timezone.utc)


def _private_destination(folder):
    path = Path(folder)
    _reject(".." not in path.parts and "\x00" not in str(path),
            "INVALID_PRIVATE_DESTINATION")
    path = path.absolute()
    _reject(path.is_dir() and not path.is_symlink(), "DESTINATION_NOT_PREEXISTING_DIRECTORY")
    for ancestor in (path, *path.parents):
        _reject(not ancestor.is_symlink(), "SYMLINK_PRIVATE_DESTINATION")
        # No business/licensed raw bytes or user's screenshots inside any Git worktree.
        _reject(not (ancestor / ".git").exists(), "GIT_WORKTREE_RAW_ARCHIVE_FORBIDDEN")
    return path


def _tar(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in (*MAXIMUMS, "receipt.json"):
            raw = files[name]
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            member.uid = member.gid = member.mtime = 0
            member.mode = 0o600
            member.uname = member.gname = ""
            archive.addfile(member, io.BytesIO(raw))
    payload = stream.getvalue()
    _reject(0 < len(payload) <= MAX_ARCHIVE_BYTES, "PRIVATE_CANDIDATE_ARCHIVE_TOO_LARGE")
    return payload


def seal_candidate(*, fixture, observations, quote, screenshot_bytes,
                   screenshot_manifest, source_raw_bytes, quote_raw_bytes,
                   fixture_seal_bytes, destination, now=None):
    """Store one non-overwritable private tar. No real feed or witness is called.

    now is injected solely for isolated deterministic tests. Production callers
    should omit it so the process wall clock is used, which is *still* not TSA.
    """
    _reject(type(fixture) is dict and type(observations) is list and type(quote) is dict
            and type(screenshot_manifest) is dict, "INVALID_CANDIDATE_FIELDS")
    _reject(type(source_raw_bytes) is dict and set(source_raw_bytes) == set(SCORES),
            "MISSING_RAW_SCORE_OR_DUPLICATE")
    try:
        provider_ids = fixture["provider_event_ids"]
        _reject(type(provider_ids) is dict and len(provider_ids) == 2,
                "INVALID_PRESEALED_PROVIDER_IDS")
        declared = [o["provider"] for o in observations]
        _reject(len(declared) == 2 and len(set(declared)) == 2
                and set(declared) == set(provider_ids), "RAW_SOURCE_IDENTITY_AMBIGUOUS")
        # Fixed identity map determines which original belongs to each source.
        _reject(type(fixture.get("source_raw_order")) is list
                and fixture["source_raw_order"] == declared,
                "SOURCE_RAW_ORDER_NOT_PRESEALED")
    except (KeyError, TypeError, ValueError):
        raise CandidateSealError("SOURCE_RAW_ORDER_NOT_PRESEALED") from None

    subjects = {
        "fixture_seal.json": fixture_seal_bytes,
        "score_primary.raw": source_raw_bytes["score_primary"],
        "score_secondary.raw": source_raw_bytes["score_secondary"],
        "quote.raw": quote_raw_bytes,
        "screenshot.raw": screenshot_bytes,
    }
    for name, limit in MAXIMUMS.items():
        raw = subjects[name]
        _reject(type(raw) is bytes and 0 < len(raw) <= limit,
                "INVALID_OR_OVERSIZED_RAW_SUBJECT:" + name)
    _validate_seal(fixture, fixture_seal_bytes)
    clock = _read_now(now)
    report = audit_claims(fixture, observations, quote, screenshot_bytes,
                          screenshot_manifest, clock.isoformat())
    _reject(report.get("status") == "RESEARCH_ONLY"
            and report.get("structure_consistent") is True
            and report.get("decision") == "HOLD"
            and report.get("production_recommendations") == "DISABLED"
            and report.get("positive_ev_verified") is False
            and report.get("bookmaker_price_executable_verified") is False
            and type(report.get("candidate_manifest")) is dict,
            "INPLAY_CROSS_SOURCE_GATE_HOLD")
    archive_folder = _private_destination(destination)
    # These are locally computed hashes of the supplied bytes, not trusted source proofs.
    digests = {name: hashlib.sha256(raw).hexdigest() for name, raw in subjects.items()}
    receipt = {
        "schema": SCHEMA,
        "capture_wall_clock_utc_not_attested": clock.isoformat(),
        "origin": "UNAUTHENTICATED_OPERATOR_RAW_BYTES",
        "fixture_id": fixture["fixture_id"],
        "file_sha256": digests,
        "file_lengths": {name: len(raw) for name, raw in subjects.items()},
        "binding_manifest_sha256": hashlib.sha256(
            _canonical_json(report["candidate_manifest"])).hexdigest(),
        "allowed_for_public_repository": False,
        "external_timestamp_verified": False,
        "fixture_identity_authenticity_verified": False,
        "independent_sources_authenticated": False,
        "source_raw_bytes_parsed_or_authenticated": False,
        "market_executable_verified": False,
        "model_scoring_eligible": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
        "decision": "HOLD",
        "certified_forward_samples": 0,
    }
    files = {**subjects, "receipt.json": _canonical_json(receipt) + b"\n"}
    archive = _tar(files)
    digest = hashlib.sha256(archive).hexdigest()
    filename = "candidate-" + clock.strftime("%Y%m%dT%H%M%SZ") + "-" + digest[:16] + ".tar"
    target = archive_folder / filename
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags, 0o600)
    except FileExistsError:
        raise CandidateSealError("IMMUTABLE_CANDIDATE_COLLISION") from None
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(archive)
            stream.flush()
            os.fsync(stream.fileno())
        _reject(stat.S_ISREG(target.lstat().st_mode), "INVALID_WRITTEN_PRIVATE_ARCHIVE")
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {
        "schema": SCHEMA, "status": "RESEARCH_ONLY", "decision": "HOLD",
        "reason": "PRIVATE_LOCAL_CAPTURE_ONLY_NO_EXTERNAL_ATTESTATION",
        "private_archive": str(target), "archive_sha256": digest,
        "capture_wall_clock_utc_not_attested": clock.isoformat(),
        "production_recommendations": "DISABLED", "positive_ev_verified": False,
        "model_scoring_eligible": False, "certified_forward_samples": 0,
    }
