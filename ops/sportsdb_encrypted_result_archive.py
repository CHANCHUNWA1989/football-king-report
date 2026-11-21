"""Encrypt one already-replayed private result observation to the pinned PQ age recipient.

Only ciphertext and non-sensitive hashes may leave the private runner.
This is transport preservation, not independent result certification.
"""
import argparse
import hashlib
import json
from pathlib import Path

from ops import private_response_relay as relay
from ops import sportsdb_result_private_archive as evidence
from ops.sportsdb_event_capture import FIXED_EVENTS

MAX_CIPHERTEXT_BYTES = evidence.MAX_PACK_BYTES + 100_000


class EncryptionError(ValueError):
    """Fixed public-safe error codes only."""


def encrypt(private_dir, output_dir, *, event_id, age_binary, recipient_file):
    if type(event_id) is not str or event_id not in FIXED_EVENTS:
        raise EncryptionError("UNSUPPORTED_RESULT_EVENT")
    if not isinstance(output_dir, Path):
        raise EncryptionError("INVALID_ENCRYPTED_OUTPUT")
    raw, manifest, proof = evidence._safe_read(private_dir, event_id)
    original = evidence._encode(raw, manifest)
    try:
        recipient = relay._recipient(
            relay._read(Path(recipient_file), 4096, private=False).decode("ascii").strip())
        ciphertext = relay._crypto(original, ["--encrypt", "-r", recipient],
                                   Path(age_binary), maximum=MAX_CIPHERTEXT_BYTES)
    except Exception:
        raise EncryptionError("PINNED_ENCRYPTION_UNAVAILABLE") from None
    if type(ciphertext) is not bytes or not 0 < len(ciphertext) <= MAX_CIPHERTEXT_BYTES:
        raise EncryptionError("INVALID_ENCRYPTED_BYTES")
    try:
        cipher_path = output_dir / (event_id + ".age")
        receipt_path = output_dir / (event_id + ".receipt.json")
        # relay._write rejects symlinks and requires a pre-existing private 0700 parent.
        relay._write(cipher_path, ciphertext)
        receipt = {
            "schema": "football-king-sportsdb-age-ciphertext-v1",
            "status": "HOLD", "event_id": event_id,
            "encryption": "age-v1.3.2-native-pq",
            "original_sha256": hashlib.sha256(original).hexdigest(),
            "raw_sha256": proof["raw_sha256"],
            "recipient_sha256": hashlib.sha256(recipient.encode("ascii")).hexdigest(),
            "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
            "ciphertext_bytes": len(ciphertext),
            "actual_kickoff_authenticated": False,
            "upstream_independence_authenticated": False,
            "independently_verified": False,
            "production_recommendations": "DISABLED",
        }
        relay._write(receipt_path, (json.dumps(receipt, sort_keys=True) + "\n").encode())
        if relay._read(cipher_path, MAX_CIPHERTEXT_BYTES, private=True) != ciphertext:
            raise EncryptionError("LOCAL_CIPHERTEXT_CHANGED")
        if json.loads(relay._read(receipt_path, 4_096, private=True)) != receipt:
            raise EncryptionError("LOCAL_RECEIPT_CHANGED")
        return receipt
    except EncryptionError:
        raise
    except Exception:
        raise EncryptionError("ENCRYPTED_OUTPUT_REJECTED") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--event-id", choices=sorted(FIXED_EVENTS), required=True)
    parser.add_argument("--age-binary", type=Path, required=True)
    parser.add_argument("--recipient-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = encrypt(args.private_dir, args.output_dir,
                         event_id=args.event_id, age_binary=args.age_binary,
                         recipient_file=args.recipient_file)
        print(json.dumps(result, sort_keys=True))
        return 0
    except EncryptionError as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc),
                          "independently_verified": False,
                          "production_recommendations": "DISABLED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
