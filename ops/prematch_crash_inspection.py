"""Read-only crash damage inspection and explicitly operator-controlled repair.

Never silently truncates an evidence ledger. Repair creates an immutable
quarantine copy and only removes an invalid trailing fragment after approval.
This cannot prove durability across real power loss or detect valid-prefix truncation.
"""
import hashlib
import json
import os
from pathlib import Path
from prematch_evidence_chain import verify_evidence_chain


def inspect_crash_tail(directory):
    root = Path(directory)
    ledger = root / "evidence-ledger.jsonl"
    result = {"status": "HOLD", "reason": "UNKNOWN",
              "production_recommendations": "DISABLED"}
    if not root.is_dir() or root.is_symlink() or ledger.is_symlink():
        return {**result, "reason": "UNSAFE_LEDGER_PATH"}
    try:
        fd = os.open(ledger, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return {**result, "reason": "LEDGER_NOT_FOUND"}
    try:
        st = os.fstat(fd)
        if not os.path.isfile(ledger) or st.st_nlink != 1 or st.st_size > 50_000_000:
            return {**result, "reason": "UNSAFE_LEDGER_INODE"}
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(50_000_001)
    finally:
        os.close(fd)
    try:
        entries = verify_evidence_chain(root)
        return {"status": "RESEARCH_ONLY", "reason": "CHAIN_VALID",
                "entries": len(entries), "production_recommendations": "DISABLED"}
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
        pass
    end = raw.rfind(b"\n")
    prefix = raw[:end + 1] if end >= 0 else b""
    tail = raw[end + 1:]
    if not tail or not prefix:
        return {**result, "reason": "CORRUPTION_REQUIRES_MANUAL_INVESTIGATION"}
    # Validate prefix without modifying original evidence.
    import tempfile
    from prematch_raw_archive import replay_response
    previous = "0" * 64
    count = 0
    try:
        for line in prefix.splitlines(keepends=True):
            if len(line) > 4096:
                raise ValueError("oversized row")
            row = json.loads(line)
            if (set(row) != {"index", "archive_sha256", "previous_hash", "entry_hash"}
                    or row["index"] != count or row["previous_hash"] != previous):
                raise ValueError("broken prefix")
            digest = row["archive_sha256"]
            if not isinstance(digest, str) or len(digest) != 64 or any(
                    ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("invalid digest")
            from prematch_evidence_chain import _encode
            if hashlib.sha256(_encode({k: v for k, v in row.items()
                                      if k != "entry_hash"})).hexdigest() != row["entry_hash"]:
                raise ValueError("broken hash")
            replay_response(root / (digest + ".json"), expected_sha256=digest)
            previous = row["entry_hash"]
            count += 1
    except (ValueError, OSError, TypeError, KeyError):
        return {**result, "reason": "CORRUPTION_REQUIRES_MANUAL_INVESTIGATION"}
    return {"status": "HOLD", "reason": "PARTIAL_TRAILING_RECORD",
            "valid_prefix_entries": count, "invalid_tail_bytes": len(tail),
            "ledger_sha256": hashlib.sha256(raw).hexdigest(),
            "valid_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
            "operator_action": "PRESERVE_ORIGINAL_AND_MANUALLY_RESTORE",
            "production_recommendations": "DISABLED"}
