"""Non-clobbering output for private research receipts and reviews.

Create a NEW regular file with owner-only permissions. Never silently replace
previous pre-match pins, score inputs, signed proof or review reports.
"""
import json
import os


def write_new_private_json(path, payload):
    data = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(os.fspath(path), flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
