"""Offline RFC3161 handoff for an *entire* private in-play candidate tar.

OpenSSL signs/verifies only the SHA256 digest; raw sportsbook bytes never leave
this function. Requires separately provided TSA response and CA trust file.
An OpenSSL pass proves only cryptographic consistency under supplied trust
anchors, NOT issuer policy, revocation, provider identity or live bookability.
Never promotes a candidate to an actual prospective prediction.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile
from datetime import datetime, timedelta, timezone

from inplay_forward_private_seal import SCHEMA as SEAL_SCHEMA, MAXIMUMS, MAX_ARCHIVE_BYTES

SCHEMA = "football-king-inplay-rfc3161-handoff-research-v1"
MEMBERS = tuple(MAXIMUMS) + ("receipt.json",)
STAMP = re.compile(r"^Time stamp:\s*([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\d{4})\s+GMT\s*$", re.MULTILINE)
NAME = re.compile(r"candidate-(\d{8}T\d{6}Z)-([0-9a-f]{16})\.tar\Z")
MAX_TIME_LAG = timedelta(seconds=120)


class TimestampHandoffError(ValueError):
    """Public-safe static error messages, never raw source contents."""


def _require(test, reason):
    if not test:
        raise TimestampHandoffError(reason)


def _read_regular(path, limit):
    p = Path(path)
    _require(".." not in p.parts, "UNSAFE_INPUT_PATH")
    try:
        before = p.lstat()
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                 0 < before.st_size <= limit, "INVALID_OR_OVERSIZED_FILE")
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as f:
            after = os.fstat(f.fileno())
            _require(stat.S_ISREG(after.st_mode) and after.st_nlink == 1 and
                     (before.st_dev, before.st_ino, before.st_size) ==
                     (after.st_dev, after.st_ino, after.st_size),
                     "FILE_CHANGED_DURING_READ")
            data = f.read(limit + 1)
        _require(len(data) == before.st_size, "FILE_CHANGED_DURING_READ")
        return data
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, TimestampHandoffError):
            raise
        raise TimestampHandoffError("UNREADABLE_PRIVATE_FILE") from None


def _unique(items):
    result = {}
    for key, val in items:
        _require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = val
    return result


def _nonfinite(_):
    raise TimestampHandoffError("NONFINITE_JSON_VALUE")


def _parse_json(raw):
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                            parse_constant=_nonfinite)
        _require(type(result) is dict, "INVALID_RECEIPT_JSON")
        return result
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise TimestampHandoffError("INVALID_RECEIPT_JSON") from None


def _utc(value):
    _require(type(value) is str and len(value) <= 64, "INVALID_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(dt.tzinfo is not None and dt.utcoffset() is not None,
                 "NAIVE_TIMESTAMP")
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError, TypeError):
        raise TimestampHandoffError("INVALID_TIMESTAMP") from None


def _inspect_archive(path):
    p = Path(path)
    match = NAME.fullmatch(p.name)
    _require(match is not None, "NOT_A_PRIVATE_CANDIDATE_ARCHIVE")
    blob = _read_regular(p, MAX_ARCHIVE_BYTES)
    whole_digest = hashlib.sha256(blob).hexdigest()
    _require(whole_digest.startswith(match.group(2)), "ARCHIVE_FILENAME_DIGEST_CONFLICT")
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as package:
            members = package.getmembers()
            _require(tuple(m.name for m in members) == MEMBERS,
                     "UNEXPECTED_OR_DUPLICATE_ARCHIVE_MEMBERS")
            data = {}
            for entry in members:
                limit = MAXIMUMS.get(entry.name, 128_000)
                _require(entry.isfile() and entry.type == tarfile.REGTYPE and
                         entry.mode == 0o600 and entry.uid == 0 and entry.gid == 0 and
                         entry.mtime == 0 and 0 < entry.size <= limit and
                         not entry.pax_headers and not entry.linkname,
                         "UNSAFE_ARCHIVE_MEMBER")
                source = package.extractfile(entry)
                _require(source is not None, "UNREADABLE_ARCHIVE_MEMBER")
                raw = source.read(limit + 1)
                _require(len(raw) == entry.size, "TRUNCATED_ARCHIVE_MEMBER")
                data[entry.name] = raw
    except (tarfile.TarError, EOFError, OSError, OverflowError):
        raise TimestampHandoffError("INVALID_PRIVATE_ARCHIVE") from None
    receipt = _parse_json(data["receipt.json"])
    fixture = _parse_json(data["fixture_seal.json"])
    _require(receipt.get("schema") == SEAL_SCHEMA and
             receipt.get("origin") == "UNAUTHENTICATED_OPERATOR_RAW_BYTES" and
             receipt.get("allowed_for_public_repository") is False and
             receipt.get("external_timestamp_verified") is False and
             receipt.get("model_scoring_eligible") is False and
             receipt.get("market_executable_verified") is False and
             receipt.get("positive_ev_verified") is False and
             receipt.get("production_recommendations") == "DISABLED" and
             receipt.get("decision") == "HOLD" and
             type(receipt.get("certified_forward_samples")) is int and
             receipt["certified_forward_samples"] == 0,
             "UNSAFE_OR_UNRECOGNIZED_RECEIPT")
    _require(type(receipt.get("file_sha256")) is dict and
             set(receipt["file_sha256"]) == set(MAXIMUMS) and
             type(receipt.get("file_lengths")) is dict and
             set(receipt["file_lengths"]) == set(MAXIMUMS),
             "INCOMPLETE_RAW_SUBJECT_DIGESTS")
    for name in MAXIMUMS:
        _require(receipt["file_sha256"].get(name) == hashlib.sha256(data[name]).hexdigest() and
                 type(receipt["file_lengths"].get(name)) is int and
                 receipt["file_lengths"][name] == len(data[name]),
                 "TAMPERED_RAW_SUBJECT")
    _require(fixture.get("provenance_notice") == "SELF_DECLARED_NOT_ATTESTED" and
             type(fixture.get("fixture")) is dict and
             receipt.get("fixture_id") == fixture["fixture"].get("fixture_id"),
             "UNBOUND_FIXTURE_SEAL")
    claimed = _utc(receipt.get("capture_wall_clock_utc_not_attested"))
    kickoff = _utc(fixture["fixture"].get("kickoff_utc"))
    filename_clock = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    _require(claimed.replace(microsecond=0) == filename_clock and
             kickoff < claimed < kickoff + timedelta(hours=3),
             "CLAIMED_CAPTURE_TIME_NOT_IN_PLAY")
    return whole_digest, claimed, kickoff


def _hold(reason):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "decision": "HOLD", "production_recommendations": "DISABLED",
        "cryptographic_imprint_check_passed": False,
        "issuer_policy_independently_approved": False,
        "independently_timestamped": False,
        "provider_data_authenticated": False,
        "live_market_executable_verified": False,
        "positive_ev_verified": False,
        "model_scoring_eligible": False,
        "certified_forward_samples": 0,
        "recommendation": None, "stakes": None,
    }


def make_query(archive_path, output_tsq_path, *, openssl="openssl", runner=subprocess.run):
    """Create an RFC3161 TSQ of the archive digest. Operator sends TSQ to TSA."""
    archive_digest, _, _ = _inspect_archive(archive_path)
    dest = Path(output_tsq_path)
    _require(dest.suffix == ".tsq" and not dest.is_symlink()
             and dest.parent.is_dir() and not dest.exists(),
             "UNSAFE_OR_EXISTING_QUERY_DESTINATION")
    for folder in (dest.parent.absolute(), *dest.parent.absolute().parents):
        _require(not (folder / ".git").exists(),
                 "PUBLIC_REPOSITORY_QUERY_OUTPUT_FORBIDDEN")
    try:
        result = runner([openssl, "ts", "-query", "-digest", archive_digest,
                         "-sha256", "-cert"],
                        capture_output=True, timeout=20, check=False)
        _require(result.returncode == 0 and type(result.stdout) is bytes
                 and 0 < len(result.stdout) <= 100_000, "OPENSSL_QUERY_FAILED")
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(result.stdout)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, subprocess.TimeoutExpired, TypeError):
        raise TimestampHandoffError("QUERY_CREATION_FAILED") from None
    return {
        "schema": SCHEMA, "status": "RESEARCH_ONLY",
        "reason": "OFFLINE_QUERY_CREATED_NOT_SENT_NOT_VERIFIED",
        "archive_sha256": archive_digest, "query_path": str(dest),
        "request_contains_only_archive_digest": True,
        "production_recommendations": "DISABLED", "decision": "HOLD",
        "independently_timestamped": False, "certified_forward_samples": 0,
    }


def verify_response(archive_path, query_path, response_path, trusted_ca_path,
                    *, openssl="openssl", runner=subprocess.run):
    """Verify response against exact archive DIGEST and original request nonce.

    This is only a preliminary OpenSSL crypto gate. The CA/TSA identity, policy
    and revocation must be independently reviewed by a separate release gate.
    """
    try:
        archive_digest, claimed, kickoff = _inspect_archive(archive_path)
        _read_regular(query_path, 100_000)
        _read_regular(response_path, 2_000_000)
        _read_regular(trusted_ca_path, 2_000_000)
        commands = (
            [openssl, "ts", "-verify", "-in", str(response_path),
             "-digest", archive_digest, "-CAfile", str(trusted_ca_path)],
            [openssl, "ts", "-verify", "-in", str(response_path),
             "-queryfile", str(query_path), "-CAfile", str(trusted_ca_path)],
        )
        for command in commands:
            check = runner(command, capture_output=True, text=True,
                           timeout=20, check=False)
            _require(check.returncode == 0, "OPENSSL_SIGNATURE_OR_IMPRINT_FAILED")
        parsed = runner([openssl, "ts", "-reply", "-in", str(response_path), "-text"],
                        capture_output=True, text=True, timeout=20, check=False)
        _require(parsed.returncode == 0 and type(parsed.stdout) is str and
                 len(parsed.stdout) <= 100_000, "UNREADABLE_TSA_RESPONSE")
        parts = STAMP.findall(parsed.stdout)
        _require(len(parts) == 1, "UNRECOGNIZED_TSA_TIME")
        month, day, clock, year = parts[0]
        stamp = datetime.strptime(f"{month} {day} {clock} {year}",
                                  "%b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
        # Response must have been minted promptly after capture. This only
        # checks a claimed local time, not publisher source time or a trusted NTP.
        _require(claimed - timedelta(seconds=30) <= stamp <= claimed + MAX_TIME_LAG and
                 kickoff < stamp < kickoff + timedelta(hours=3),
                 "TSA_TIME_NOT_TIMELY_FOR_THIS_CAPTURE")
        return {
            **_hold("TSA_CRYPTO_PASSED_EXTERNAL_POLICY_REVIEW_REQUIRED"),
            "status": "RESEARCH_ONLY",
            "cryptographic_imprint_check_passed": True,
            "tsa_stamped_utc": stamp.isoformat(),
            "archive_sha256": archive_digest,
        }
    except (TimestampHandoffError, ValueError, TypeError, OSError,
            subprocess.TimeoutExpired, AttributeError) as exc:
        return _hold(str(exc) if isinstance(exc, TimestampHandoffError)
                     else "TSA_VERIFICATION_ERROR")
