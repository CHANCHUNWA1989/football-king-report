"""Append-only hash-linked evidence ledger, locally verifiable not externally attested."""
import hashlib
import json
import os
from pathlib import Path


def _encode(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def append_evidence(directory, archive):
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("invalid evidence directory")
    digest = archive.get("sha256") if isinstance(archive, dict) else None
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid archive digest")
    from prematch_raw_archive import replay_response
    replay_response(root / (digest + ".json"), expected_sha256=digest)
    # Exclusive lock file avoids concurrent appenders interleaving records.
    lock = root / ".evidence.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        ledger = root / "evidence-ledger.jsonl"
        entries = verify_evidence_chain(directory)
        previous = entries[-1]["entry_hash"] if entries else "0" * 64
        payload = {"index": len(entries), "archive_sha256": digest,
                   "previous_hash": previous}
        payload["entry_hash"] = hashlib.sha256(_encode(payload)).hexdigest()
        with open(ledger, "ab") as stream:
            stream.write(_encode(payload))
            stream.flush()
            os.fsync(stream.fileno())
        return payload
    finally:
        lock.unlink(missing_ok=True)


def verify_evidence_chain(directory):
    ledger = Path(directory) / "evidence-ledger.jsonl"
    if not ledger.exists():
        return []
    entries = []
    previous = "0" * 64
    with open(ledger, "rb") as stream:
        for raw in stream:
            if len(raw) > 4096 or not raw.endswith(b"\n"):
                raise ValueError("invalid ledger record")
            row = json.loads(raw)
            if (not isinstance(row, dict) or set(row) != {
                    "index", "archive_sha256", "previous_hash", "entry_hash"}
                    or type(row["index"]) is not int or row["index"] != len(entries)
                    or row["previous_hash"] != previous):
                raise ValueError("broken evidence chain")
            digest = row["entry_hash"]
            if hashlib.sha256(_encode({k: v for k, v in row.items()
                                      if k != "entry_hash"})).hexdigest() != digest:
                raise ValueError("evidence hash mismatch")
            from prematch_raw_archive import replay_response
            replay_response(Path(directory) / (row["archive_sha256"] + ".json"),
                            expected_sha256=row["archive_sha256"])
            entries.append(row)
            previous = digest
    return entries
