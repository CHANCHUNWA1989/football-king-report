"""Read-only, zero-secret audit of two pinned encrypted historical FT observations.

Independently replay PUBLIC ciphertext digests and safety receipt pins against
expected values recorded from GitHub Actions run 42406458039. This has no
decryption key, and MUST NOT be called a verified football settlement.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

RUN_DIRECTORY = "42406458039-1"
ENCRYPTION = "age-v1.3.2-native-pq"
RECIPIENT_SHA = "a8dc3f96b0063a6fa5293e2a9e709ad5e012a6f24a54ca85fea88333d73b62ac"
MAX_CIPHER_BYTES = 600_000
MAX_RECEIPT_BYTES = 4096
EVENTS = {
    "2508371": {
        "ciphertext_sha256": "0dfd99baa4befea9f8018db6a6785044939d57c883252179d6b652d0abba7927",
        "ciphertext_bytes": 4836,
        "receipt_git_blob_sha1": "56a427dbe8ba6f4bf79f6ac94e6e55206d9fc1c2",
        "raw_sha256": "e363bd555b7d20498770b238f919fca6036f566c960807eb84096d7985e9c948",
        "original_sha256": "39565226e4e4e0d6e1a5f456072a661b5cc4db569b4b14c6c9cf2a8c8353c3e4",
    },
    "2508372": {
        "ciphertext_sha256": "025c14c1fc4c957b9c1b94432d2e26b55646944cf0d92060cef011548a6aa2e8",
        "ciphertext_bytes": 4780,
        "receipt_git_blob_sha1": "73e2d9f41da7be91ae20337a1918a0e9e4b8aa1f",
        "raw_sha256": "b62996e52d2b208b06b5b99dd3b89a0d08d57846596097ca4793992b95ce7aee",
        "original_sha256": "24980afd7513a7ace325cfe66ded8c2b22870809a5ed64f9ea8ddf52c7cc5cbc",
    },
}
RECEIPT_KEYS = {
    "schema", "status", "event_id", "encryption", "original_sha256",
    "raw_sha256", "recipient_sha256", "ciphertext_sha256",
    "ciphertext_bytes", "actual_kickoff_authenticated",
    "upstream_independence_authenticated", "independently_verified",
    "production_recommendations",
}


class PublicEvidenceError(ValueError):
    """Static code; never interpolate user-controlled text into logs."""


def _require(ok, code):
    if not ok:
        raise PublicEvidenceError(code)


def _unique(items):
    result = {}
    for key, value in items:
        _require(key not in result, "DUPLICATE_RECEIPT_KEY")
        result[key] = value
    return result


def _parse(raw):
    try:
        obj = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             PublicEvidenceError("INVALID_RECEIPT")))
    except PublicEvidenceError:
        raise
    except (TypeError, UnicodeError, ValueError, RecursionError):
        raise PublicEvidenceError("INVALID_RECEIPT") from None
    _require(type(obj) is dict and set(obj) == RECEIPT_KEYS,
             "INVALID_RECEIPT_SCHEMA")
    return obj


def _read(root, name, maximum):
    path = root / name
    try:
        before = path.lstat()
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                 and 0 < before.st_size <= maximum, "UNSAFE_EVIDENCE_FILE")
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK
                     | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            _require((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                     == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
                     "EVIDENCE_FILE_CHANGED")
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        linked = path.lstat()
        _require((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                 == (linked.st_dev, linked.st_ino, linked.st_size, linked.st_mtime_ns)
                 == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                 and len(raw) == before.st_size, "EVIDENCE_FILE_CHANGED")
        return raw
    except PublicEvidenceError:
        raise
    except (OSError, TypeError):
        raise PublicEvidenceError("MISSING_OR_UNSAFE_EVIDENCE_FILE") from None


def audit(directory):
    """Integrity audit only; no original plaintext, keys, API or live request."""
    root = Path(directory)
    _require(root.name == RUN_DIRECTORY
             and root.is_dir() and not root.is_symlink()
             and not any(parent.is_symlink() for parent in root.parents),
             "UNSAFE_EVIDENCE_DIRECTORY")
    expected_names = {event + suffix for event in EVENTS
                      for suffix in (".age", ".receipt.json")}
    _require({p.name for p in root.iterdir()} == expected_names,
             "UNEXPECTED_EVIDENCE_FILES")
    output = []
    for event_id, pins in sorted(EVENTS.items()):
        encrypted = _read(root, event_id + ".age", MAX_CIPHER_BYTES)
        receipt_bytes = _read(root, event_id + ".receipt.json", MAX_RECEIPT_BYTES)
        receipt = _parse(receipt_bytes)
        receipt_blob = hashlib.sha1(
            b"blob " + str(len(receipt_bytes)).encode("ascii") + b"\\0" + receipt_bytes
        ).hexdigest()
        _require(receipt_blob == pins["receipt_git_blob_sha1"],
                 "RECEIPT_ORIGINAL_BYTES_CHANGED")
        digest = hashlib.sha256(encrypted).hexdigest()
        _require(type(receipt["ciphertext_bytes"]) is int
                 and receipt["ciphertext_bytes"] == len(encrypted)
                 and receipt["ciphertext_bytes"] == pins["ciphertext_bytes"]
                 and digest == pins["ciphertext_sha256"]
                 and receipt["ciphertext_sha256"] == digest,
                 "CIPHERTEXT_PIN_MISMATCH")
        _require(receipt["event_id"] == event_id
                 and receipt["schema"] == "football-king-sportsdb-age-ciphertext-v1"
                 and receipt["status"] == "HOLD"
                 and receipt["encryption"] == ENCRYPTION
                 and receipt["recipient_sha256"] == RECIPIENT_SHA
                 and receipt["raw_sha256"] == pins["raw_sha256"]
                 and receipt["original_sha256"] == pins["original_sha256"]
                 and receipt["independently_verified"] is False
                 and receipt["actual_kickoff_authenticated"] is False
                 and receipt["upstream_independence_authenticated"] is False
                 and receipt["production_recommendations"] == "DISABLED",
                 "RECEIPT_CLAIM_OR_PIN_MISMATCH")
        output.append({"provider_event_id": event_id, "ciphertext_sha256": digest,
                       "ciphertext_bytes": len(encrypted),
                       "ciphertext_integrity_matched": True,
                       "receipt_pins_matched": True,
                       "decryption_performed": False,
                       "source_outcome_authenticated": False,
                       "independently_verified": False})
    return {"schema": "football-king-public-encrypted-evidence-audit-v1",
            "status": "HOLD", "observed_event_count": len(output),
            "checks": output, "ciphertext_integrity_verified": True,
            "receipt_pins_verified": True,
            "raw_post_decryption_replay_verified": False,
            "upstream_independence_authenticated": False,
            "actual_kickoff_authenticated": False,
            "certified_case_count": 0,
            "production_recommendations": "DISABLED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.directory)
    except (PublicEvidenceError, OSError) as exc:
        reason = str(exc) if isinstance(exc, PublicEvidenceError) else "PUBLIC_AUDIT_IO_REJECTED"
        print(json.dumps({"status": "HOLD", "reason": reason,
                          "ciphertext_integrity_verified": False,
                          "certified_case_count": 0,
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
