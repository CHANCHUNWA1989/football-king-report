"""Optional private, same-GET original-A raw source preservation.

The caller passes bytes already read by the original A fixture gateway. No
second HTTP request, no secret, no publisher authentication, no external time
witness, no claim of a genuine prospective training/quote sample. The sealed
subject is a LOCAL unverified research artifact and MUST NOT be published.
"""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tarfile
import tempfile

SCHEMA = "football-king-original-a-same-get-private-candidate-v1"
MAX_BODY = 8_000_000
MAX_TAR = 8_100_000
MAX_METADATA = 8192
NAMES = ("manifest.json", "openligadb.json")


def _utc(v):
    if type(v) is not str or not 10 < len(v) <= 70:
        raise ValueError("INVALID_SOURCE_GATEWAY_TIMESTAMP")
    try:
        value = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("INVALID_SOURCE_GATEWAY_TIMESTAMP") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("INVALID_SOURCE_GATEWAY_TIMESTAMP")
    return value.astimezone(timezone.utc)


def _private_directory(path):
    value = Path(path)
    if not value.is_absolute() or ".." in value.parts:
        raise ValueError("UNSAFE_PRIVATE_CAPTURE_DIRECTORY")
    if any(parent.is_symlink() for parent in (value, *value.parents)):
        raise ValueError("UNSAFE_PRIVATE_CAPTURE_DIRECTORY")
    try:
        info = value.stat()
    except OSError as exc:
        raise ValueError("UNAVAILABLE_PRIVATE_CAPTURE_DIRECTORY") from exc
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise ValueError("UNSAFE_PRIVATE_CAPTURE_DIRECTORY")
    return value


def _json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _bundle(metadata, body):
    manifest = _json(metadata)
    if len(manifest) > MAX_METADATA:
        raise ValueError("OVERSIZED_PRIVATE_CAPTURE_MANIFEST")
    values = {"manifest.json": manifest, "openligadb.json": body}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for name in NAMES:
            raw = values[name]
            info = tarfile.TarInfo(name)
            info.mode, info.mtime = 0o600, 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.size = len(raw)
            t.addfile(info, io.BytesIO(raw))
    result = stream.getvalue()
    if len(result) > MAX_TAR:
        raise ValueError("OVERSIZED_PRIVATE_CAPTURE_BUNDLE")
    return result


def seal(directory, *, body, original, season, league, now=None):
    """Preserve exact original HTTP body; fail closed BEFORE any promotion.

    The accepted original is the SAME gateway result normalized from body.
    The local report's source hash is just relative byte integrity, not a
    cryptographic proof of provider authenticity or timestamp custody.
    """
    location = _private_directory(directory)
    if (type(body) is not bytes or not 0 < len(body) <= MAX_BODY
            or type(original) is not dict or league != "bundesliga"
            or type(season) is not str
            or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}", season)):
        raise ValueError("INVALID_PRIVATE_SOURCE_INPUT")
    digest = hashlib.sha256(body).hexdigest()
    if (original.get("status") != "READY_RESEARCH"
            or original.get("source") != "OpenLigaDB"
            or original.get("league") != league
            or original.get("season") != season
            or original.get("sha256") != digest
            or original.get("_same_response_source_sha256") != digest):
        raise ValueError("ORIGINAL_GATEWAY_RESPONSE_HASH_MISMATCH")
    claimed = _utc(original.get("captured_utc"))
    local = datetime.now(timezone.utc) if now is None else now
    if type(local) is not datetime or local.tzinfo is None or local.utcoffset() is None:
        raise ValueError("INVALID_LOCAL_CAPTURE_CLOCK")
    local = local.astimezone(timezone.utc)
    if claimed > local:
        raise ValueError("SOURCE_GATEWAY_CLAIM_AFTER_LOCAL_SEAL")
    metadata = {
        "schema": SCHEMA,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "source": "OpenLigaDB",
        "league": league,
        "season": season,
        "body_sha256": digest,
        "body_bytes": len(body),
        "gateway_capture_utc_unattested": claimed.isoformat(),
        "local_sealed_utc_unattested": local.isoformat(),
        "same_original_get_no_second_http_request": True,
        "publisher_identity_authenticated": False,
        "independent_capture_time_verified": False,
        "raw_source_legally_authorized_for_redistribution": False,
        "eligible_for_model_scoring": False,
        "positive_ev_verified": False,
    }
    raw = _bundle(metadata, body)
    private_hash = hashlib.sha256(raw).hexdigest()
    target = location / (private_hash + ".openliga-private.tar")
    stage = None
    try:
        fd, stage = tempfile.mkstemp(prefix=".same-get-stage-", suffix=".tmp", dir=location)
        with os.fdopen(fd, "wb") as dest:
            info = os.fstat(dest.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("INVALID_PRIVATE_CAPTURE_FILE")
            dest.write(raw)
            dest.flush()
            os.fsync(dest.fileno())
        _private_directory(location)
        # Atomically create the final path IF ABSENT; never rename over prior
        # raw captures. The staging file remains private and is then unlinked.
        os.link(stage, target, follow_symlinks=False)
    finally:
        if stage is not None:
            os.unlink(stage)
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "local_raw_bytes_saved": True,
        "same_get_raw_sha256_unattested": digest,
        "private_bundle_sha256_unattested": private_hash,
        "external_timestamp_attested": False,
        "publisher_identity_authenticated": False,
        "certified_prospective_samples": 0,
        "positive_ev_verified": False,
    }


def check_private_bundle(path, *, expected_bundle_sha256, expected_raw_sha256):
    """Replay exact local saved bytes; still strictly NOT signature verification."""
    value = Path(path)
    if (value.name != expected_bundle_sha256 + ".openliga-private.tar"
            or not re.fullmatch("[0-9a-f]{64}", expected_bundle_sha256)
            or not re.fullmatch("[0-9a-f]{64}", expected_raw_sha256)):
        raise ValueError("INVALID_PRIVATE_CAPTURE_DIGEST")
    _private_directory(value.parent)
    if value.is_symlink():
        raise ValueError("UNSAFE_PRIVATE_CAPTURE_FILE")
    before = value.stat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or not 0 < before.st_size <= MAX_TAR or before.st_mode & 0o077):
        raise ValueError("INVALID_PRIVATE_CAPTURE_FILE")
    with value.open("rb") as reader:
        raw = reader.read(MAX_TAR + 1)
    if len(raw) != before.st_size or hashlib.sha256(raw).hexdigest() != expected_bundle_sha256:
        raise ValueError("PRIVATE_CAPTURE_BUNDLE_HASH_MISMATCH")
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as t:
            items = t.getmembers()
            if ([x.name for x in items] != list(NAMES)
                    or any(x.type != tarfile.REGTYPE or x.mode != 0o600
                           or x.pax_headers or x.linkname or x.mtime != 0
                           or x.uid != 0 or x.gid != 0 for x in items)):
                raise ValueError("INVALID_PRIVATE_CAPTURE_MEMBERS")
            body_manifest = t.extractfile(items[0]).read(MAX_METADATA + 1)
            body = t.extractfile(items[1]).read(MAX_BODY + 1)
            if (len(body_manifest) != items[0].size or len(body) != items[1].size):
                raise ValueError("INVALID_PRIVATE_CAPTURE_MEMBER_SIZE")
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise ValueError("INVALID_PRIVATE_CAPTURE_ARCHIVE") from exc
    def unique(pairs):
        out = {}
        for key, val in pairs:
            if key in out:
                raise ValueError("DUPLICATE_PRIVATE_MANIFEST_KEY")
            out[key] = val
        return out
    man = json.loads(body_manifest, object_pairs_hook=unique)
    if (man.get("schema") != SCHEMA or
            man.get("production_recommendations") != "DISABLED"
            or man.get("publisher_identity_authenticated") is not False
            or man.get("independent_capture_time_verified") is not False
            or man.get("eligible_for_model_scoring") is not False
            or man.get("body_bytes") != len(body) or
            man.get("body_sha256") != expected_raw_sha256 or
            hashlib.sha256(body).hexdigest() != expected_raw_sha256
            or _bundle(man, body) != raw):
        raise ValueError("PRIVATE_CAPTURE_BODY_OR_SCHEMA_MISMATCH")
    return {
        "schema": SCHEMA, "status": "HOLD",
        "production_recommendations": "DISABLED",
        "exact_same_get_bytes_locally_replayed": True,
        "publisher_identity_authenticated": False,
        "independent_capture_time_verified": False,
        "certified_prospective_samples": 0,
        "positive_ev_verified": False,
    }
