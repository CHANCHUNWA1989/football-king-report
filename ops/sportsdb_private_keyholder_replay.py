"""Optional OFFLINE key-holder-only replay of two encrypted original FT observations.

Nothing here promotes a trusted outcome. No HTTP, uploads, archive writes, or public reports containing raw JSON or identity bytes.
The pinned age subprocess uses a private ephemeral quarantine file for its
plaintext output; it is removed after success/failure, not permanently saved.
The correct native PQ
age identity MUST be held privately by an independently authorized reviewer.
The public audit and exact historical receipt pins run before any decryption.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from ops import private_response_relay as relay
from ops import sportsdb_public_cipher_audit as public
from ops import sportsdb_result_private_archive as envelope
from ops.sportsdb_event_capture import verify_capture_bytes, CaptureError, FIXED_EVENTS


class DecryptionAuditError(ValueError):
    """Constant error code only; never return child stderr or credential text."""


def _require(condition, code):
    if not condition:
        raise DecryptionAuditError(code)


def decode_original_pack(pack, *, event_id, receipt):
    """Parse exactly one authenticated decryption result in process memory."""
    _require(type(event_id) is str and event_id in FIXED_EVENTS
             and type(pack) is bytes and 0 < len(pack) <= envelope.MAX_PACK_BYTES,
             "INVALID_PACK_LENGTH_OR_EVENT")
    _require(type(receipt) is dict and receipt.get("event_id") == event_id,
             "PACK_EVENT_MISMATCH")
    _require(hashlib.sha256(pack).hexdigest() == receipt["original_sha256"],
             "DECRYPTED_PACK_PIN_MISMATCH")
    prefix = envelope.MAGIC
    _require(pack.startswith(prefix) and len(pack) >= len(prefix) + 4,
             "INVALID_PACK_MAGIC")
    size_start = len(prefix)
    count = int.from_bytes(pack[size_start:size_start + 4], "big")
    _require(0 < count <= envelope.MANIFEST_LIMIT,
             "INVALID_PACK_MANIFEST_LENGTH")
    payload_start = size_start + 4
    _require(payload_start + count < len(pack),
             "INVALID_PACK_LENGTH")
    manifest = pack[payload_start:payload_start + count]
    raw = pack[payload_start + count:]
    _require(0 < len(raw) <= 512_000
             and hashlib.sha256(raw).hexdigest() == receipt["raw_sha256"],
             "DECRYPTED_RAW_PIN_MISMATCH")
    try:
        observation = verify_capture_bytes(raw, manifest, event_id=event_id, require_live=True)
    except (CaptureError, ValueError, TypeError, KeyError):
        raise DecryptionAuditError("DECRYPTED_SOURCE_RECEIPT_REPLAY_FAILED") from None
    _require(observation["raw_integrity_replayed"] is True
             and observation["raw_sha256"] == receipt["raw_sha256"]
             and observation["provider_event_id"] == event_id
             and observation["independently_verified"] is False,
             "DECRYPTED_SOURCE_RECEIPT_REPLAY_FAILED")
    return {
        "provider_event_id": event_id,
        "decrypted_original_pack_sha256": hashlib.sha256(pack).hexdigest(),
        "decrypted_raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
        "private_memory_replay": True,
        "private_identity_stored_in_public_repo": False,
        "publisher_truth_authenticated": False,
        "upstream_independence_authenticated": False,
        "actual_kickoff_authenticated": False,
        "independently_verified": False,
        "production_recommendations": "DISABLED",
        "status": "HOLD",
    }


def replay(directory, *, event_id, identity_file, age_binary):
    """Audited public ciphertext + private key; no durable plaintext archive."""
    _require(type(event_id) is str and event_id in public.EVENTS,
             "UNSUPPORTED_ENCRYPTED_EVENT")
    root = Path(directory)
    # Checking ALL historical objects first prevents accepting truncated packs.
    published = public.audit(root)
    _require(published["ciphertext_integrity_verified"] is True
             and published["receipt_pins_verified"] is True,
             "PUBLIC_PIN_REPLAY_FAILED")
    ciphertext = public._read(root, event_id + ".age", public.MAX_CIPHER_BYTES)
    receipt_bytes = public._read(root, event_id + ".receipt.json",
                                 public.MAX_RECEIPT_BYTES)
    pins = public.EVENTS[event_id]
    receipt = public._parse(receipt_bytes)
    _require(hashlib.sha256(ciphertext).hexdigest() == pins["ciphertext_sha256"]
             and hashlib.sha1(
                 b"blob " + str(len(receipt_bytes)).encode() + bytes([0]) + receipt_bytes
             ).hexdigest() == pins["receipt_git_blob_sha1"]
             and receipt["event_id"] == event_id
             and receipt["original_sha256"] == pins["original_sha256"],
             "PUBLIC_PIN_CHANGED_DURING_REPLAY")
    # relay._read checks 0700 private parent / 0600 regular file and refuses
    # symlink chains, repository paths, unsafe ownership and changed inodes.
    try:
        identity = relay._read(Path(identity_file), 8_000, private=True)
        lines = [line for line in identity.decode("ascii").splitlines()
                 if line and not line.startswith("#")]
        _require(len(lines) == 1 and re.fullmatch(
                 r"AGE-SECRET-KEY-PQ-1[A-Z0-9]{40,4096}", lines[0]) is not None,
                 "PRIVATE_IDENTITY_FORMAT_REJECTED")
        original = relay._crypto(ciphertext, ["--decrypt"],
                                 Path(age_binary), identity=identity,
                                 maximum=envelope.MAX_PACK_BYTES)
    except DecryptionAuditError:
        raise
    except Exception:
        raise DecryptionAuditError("PRIVATE_KEY_OR_PINNED_DECRYPTION_UNAVAILABLE") from None
    return decode_original_pack(original, event_id=event_id, receipt=receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--event-id", required=True, choices=sorted(public.EVENTS))
    parser.add_argument("--identity-file", type=Path, required=True,
                        help="0700 private parent / 0600 local age PQ key; never upload")
    parser.add_argument("--age-binary", type=Path, required=True,
                        help="pinned age v1.3.2 binary installed by ops.install_age")
    args = parser.parse_args(argv)
    try:
        result = replay(args.directory, event_id=args.event_id,
                        identity_file=args.identity_file, age_binary=args.age_binary)
    except (DecryptionAuditError, public.PublicEvidenceError, OSError):
        # Intentionally static; no raw source, GitHub path, key, stderr or API body.
        print(json.dumps({
            "status": "HOLD", "reason": "PRIVATE_REPLAY_REJECTED_OR_UNAVAILABLE",
            "raw_post_decryption_replay_verified": False,
            "independently_verified": False,
            "certified_case_count": 0, "production_recommendations": "DISABLED",
        }, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
