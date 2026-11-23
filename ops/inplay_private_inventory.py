"""Read-only reconciliation of create-only *private* in-play claim archives.

This is an OFFLINE, operator-pinned inventory check for PR537 local files, not
a listing service, remote WORM store, authenticated capture, audit signature,
timestamp authority, provider license or model admission. Only synthetic
research fixtures are allowed in CI; never print any private archive bytes.
"""
import hashlib
import os

from ops import private_response_capture as private
from inplay_private_claim_replay import MAX_PACKAGE_BYTES, replay_private_package
from inplay_private_local_store import _filename, _report, _root_fd, StoreError

SCHEMA = "football-king-private-inplay-inventory-v1"
MAX_PACKAGES = 64
COMMITMENT_PREFIX = b"football-king-private-inplay-inventory-v1\x00"


def _hold():
    return {
        **_report("PRIVATE_INVENTORY_MISSING_UNSAFE_OR_CHANGED"),
        "schema": SCHEMA,
        "all_expected_packages_replayed": False,
        "verified_package_count": 0,
        "inventory_sha256_unattested": None,
    }


def audit_private_inventory(root, expected_sha256, *, now=None):
    """Check EXACT expected digest-named files in a private directory.

    The caller MUST independently retain and verify the expected digest list.
    Without independently witnessed pins, a completely replaced inventory
    could still look self-consistent. This never creates, deletes, renames,
    uploads, or reveals any archive, path, filename, or original source URL.
    """
    descriptor = None
    reopened = None
    try:
        if (type(expected_sha256) is not list
                or not 1 <= len(expected_sha256) <= MAX_PACKAGES):
            raise StoreError("INVALID_PRIVATE_INVENTORY_PINS")
        names = [_filename(value) for value in expected_sha256]
        if len(set(names)) != len(names):
            raise StoreError("DUPLICATE_PRIVATE_INVENTORY_PINS")
        expected_names = set(names)
        ordered = sorted(zip(expected_sha256, names))
        commitment_bytes = b"football-king-private-inplay-inventory-v1\x00" + (
            b"\x00".join(name.encode("ascii") for _, name in ordered))
        commitment = hashlib.sha256(commitment_bytes).hexdigest()

        descriptor = _root_fd(root)
        if set(os.listdir(descriptor)) != expected_names:
            raise StoreError("PRIVATE_INVENTORY_ENTRY_MISMATCH")

        for digest, name in ordered:
            raw = private._read(descriptor, name, MAX_PACKAGE_BYTES)
            if hashlib.sha256(raw).hexdigest() != digest:
                raise StoreError("PRIVATE_INVENTORY_DIGEST_MISMATCH")
            result = replay_private_package(raw, now=now)
            if result["status"] != "RESEARCH_ONLY":
                raise StoreError("PRIVATE_INVENTORY_REPLAY_FAILED")

        if set(os.listdir(descriptor)) != expected_names:
            raise StoreError("PRIVATE_INVENTORY_CHANGED_DURING_SCAN")
        # A second full read catches many mid-scan replacements or mutations.
        for digest, name in ordered:
            raw = private._read(descriptor, name, MAX_PACKAGE_BYTES)
            if hashlib.sha256(raw).hexdigest() != digest:
                raise StoreError("PRIVATE_INVENTORY_CHANGED_DURING_SCAN")
        if set(os.listdir(descriptor)) != expected_names:
            raise StoreError("PRIVATE_INVENTORY_CHANGED_DURING_SCAN")

        # Re-open the path: do not claim a successful inventory for an
        # unlinked or replaced private root directory.
        reopened = _root_fd(root)
        if private._identity(os.fstat(descriptor)) != private._identity(os.fstat(reopened)):
            raise StoreError("PRIVATE_INVENTORY_ROOT_REPLACED")

        return {
            **_hold(),
            "status": "RESEARCH_ONLY",
            "reason": "LOCAL_PRIVATE_INVENTORY_SELF_CONSISTENT_NOT_ATTESTED",
            "local_filesystem_byte_readback_verified": True,
            "all_expected_packages_replayed": True,
            "verified_package_count": len(ordered),
            "inventory_sha256_unattested": commitment,
        }
    except (StoreError, private.CaptureError, OSError, ValueError, TypeError,
            KeyError, AttributeError, RecursionError, OverflowError):
        return _hold()
    finally:
        if reopened is not None:
            os.close(reopened)
        if descriptor is not None:
            os.close(descriptor)
