"""Create-only local private storage for untrusted synthetic/live *claim* bundles.

Accepts a PR535 in-memory package. Uses directory and file primitives already
used by private_response_capture: NOFOLLOW traversals, 0700 owner directory,
0600 single-link files, O_EXCL, readback and fsync. This is local filesystem
integrity ONLY, not WORM, a real provider receipt, remote preservation,
signed timestamp, source independence, forward evidence or betting admission.

Operator must provision a dedicated 0700 directory OUTSIDE any git checkout.
The adapter never creates that directory, logs raw bytes, or uploads a package.
"""
import hashlib
import os
import re
import stat

from ops import private_response_capture as private
from inplay_private_claim_replay import MAX_PACKAGE_BYTES, replay_private_package

SCHEMA = "football-king-inplay-private-local-readback-v1"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
PREFIX = "inplay-"
SUFFIX = ".tar"


class StoreError(ValueError):
    """Safe fixed error codes only. Never return local paths or contents."""


def _report(reason="PRIVATE_PACKAGE_NOT_VERIFIED"):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "local_filesystem_byte_readback_verified": False,
        "created_new_private_file": False,
        "durable_storage_independently_verified": False,
        "raw_source_publisher_authenticated": False,
        "source_independence_verified": False,
        "externally_witnessed": False,
        "signed_timestamp_verified": False,
        "eligible_for_model_input": False,
        "eligible_for_model_scoring": False,
        "positive_ev_verified": False,
        "certified_forward_samples": 0,
        "production_recommendations": "DISABLED",
        "recommendation": None,
        "roi": None,
        "package_sha256_unattested": None,
    }


def _filename(digest):
    if type(digest) is not str or DIGEST.fullmatch(digest) is None:
        raise StoreError("INVALID_PRIVATE_PACKAGE_PIN")
    return PREFIX + digest + SUFFIX


def _root_fd(root):
    descriptor = None
    try:
        path = private._path(root)
        descriptor = private._open_chain(path)
        private._directory_mode(descriptor)
        return descriptor
    except (ValueError, TypeError, OSError, private.CaptureError):
        if descriptor is not None:
            os.close(descriptor)
        raise StoreError("UNSAFE_OR_MISSING_PRIVATE_DIRECTORY") from None


def _read_verified(descriptor, name, expected_digest):
    raw = private._read(descriptor, name, MAX_PACKAGE_BYTES)
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise StoreError("PRIVATE_PACKAGE_BYTES_CHANGED")
    return raw


def _write_once(descriptor, name, raw):
    fd = None
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=descriptor)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(descriptor)
    except (ValueError, TypeError, OSError):
        if fd is not None:
            os.close(fd)
        # A partial file may remain following a real disk failure; never
        # silently overwrite/retry or treat that write as successful.
        raise StoreError("PRIVATE_CREATE_ONLY_WRITE_FAILED") from None


def save_private_package(root, package, *, now=None):
    """Create exactly one private file; byte-identical retries are no-ops.

    Caller supplies local, private PR535 package bytes. No provider collection,
    no private GitHub API transport, no automatic encryption or backup.
    """
    if type(package) is not bytes or not 0 < len(package) <= MAX_PACKAGE_BYTES:
        raise StoreError("INVALID_PRIVATE_PACKAGE_INPUT")
    replay = replay_private_package(package, now=now)
    if replay["status"] != "RESEARCH_ONLY":
        raise StoreError("PRIVATE_PACKAGE_REPLAY_REJECTED")
    digest = hashlib.sha256(package).hexdigest()
    name = _filename(digest)
    descriptor = _root_fd(root)
    created = False
    try:
        try:
            os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            _write_once(descriptor, name, package)
            created = True
        recorded = _read_verified(descriptor, name, digest)
        if recorded != package:
            raise StoreError("PRIVATE_PACKAGE_COLLISION")
        confirmed = replay_private_package(recorded, now=now)
        if confirmed["status"] != "RESEARCH_ONLY":
            raise StoreError("PRIVATE_PACKAGE_READBACK_REJECTED")
        return {**_report("EXACT_LOCAL_PRIVATE_BYTES_READBACK_NOT_ATTESTED"),
                "status": "RESEARCH_ONLY",
                "local_filesystem_byte_readback_verified": True,
                "created_new_private_file": created,
                "package_sha256_unattested": digest,
                "packet_sha256_unattested": confirmed["packet_sha256_unattested"]}
    except StoreError:
        raise
    except (OSError, ValueError, TypeError, private.CaptureError):
        raise StoreError("PRIVATE_LOCAL_STORE_REJECTED") from None
    finally:
        os.close(descriptor)


def verify_private_package(root, expected_sha256, *, now=None):
    """Read exact file by digest and replay. No listing of other stored packs."""
    try:
        name = _filename(expected_sha256)
        descriptor = _root_fd(root)
        try:
            package = _read_verified(descriptor, name, expected_sha256)
        finally:
            os.close(descriptor)
        replay = replay_private_package(package, now=now)
        if replay["status"] != "RESEARCH_ONLY":
            return _report("PRIVATE_REPLAY_FAILED")
        return {**_report("EXACT_LOCAL_PRIVATE_BYTES_READBACK_NOT_ATTESTED"),
                "status": "RESEARCH_ONLY",
                "local_filesystem_byte_readback_verified": True,
                "package_sha256_unattested": expected_sha256,
                "packet_sha256_unattested": replay["packet_sha256_unattested"]}
    except (StoreError, ValueError, OSError, TypeError, private.CaptureError):
        return _report("INVALID_OR_UNAVAILABLE_PRIVATE_PACKAGE")
