"""Read large private history from an explicitly mounted local file.

This module does not fetch public URLs or print data. A caller must provision
the file privately and pin its expected SHA-256 independently.
"""
import hashlib
import hmac
from pathlib import Path
from ops.private_history_intake import load

MAX_BYTES = 2_000_000


def load_pinned(path, expected_sha256):
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha256)):
        raise ValueError("INVALID_HISTORY_PIN")
    p = Path(path)
    if not p.is_file() or p.is_symlink() or not 0 < p.stat().st_size <= MAX_BYTES:
        raise ValueError("INVALID_PRIVATE_HISTORY_FILE")
    raw = p.read_bytes()
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_sha256):
        raise ValueError("HISTORY_DIGEST_MISMATCH")
    return load(p)
