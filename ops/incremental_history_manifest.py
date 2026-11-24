"""Incremental immutable gzip manifest check: local Git only, always HOLD.

Prior SHA-256 values are inherited, not independently rehashed. Exact source
tree identities and complete append-only diffs are checked; only novel Git
blob IDs are read and SHA-256 hashed. No remote access, storage writes, or
release authority. Use a full trusted local Git object store for both pins.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from ops.history_blob_retention_preflight import (
    RetentionHold, _validate, _unique, _git, _blob, _valid_sha, _path,
)

LIMIT = 262144


def _decode(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= LIMIT:
        raise RetentionHold("INCREMENT_MANIFEST_SIZE")
    return json.loads(raw, object_pairs_hook=_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          RetentionHold("NONFINITE_MANIFEST_VALUE")))


def _git_blob_id(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _index_by_blob(entries):
    index = {}
    for row in entries.values():
        oid = row["git_blob_sha1"]
        value = (row["compressed_bytes"], row["sha256_compressed"])
        if oid in index and index[oid] != value:
            raise RetentionHold("INCREMENT_CONFLICTING_BLOB_DIGEST")
        index[oid] = value
    return index


def lineage(previous_raw, current_raw):
    old, new = _decode(previous_raw), _decode(current_raw)
    a, b = _validate(old), _validate(new)
    if (new["archive_bootstrap_sha"] != old["archive_bootstrap_sha"]
            or new["source_main_sha"] == old["source_main_sha"]
            or new.get("previous_source_main_sha") != old["source_main_sha"]
            or new.get("previous_manifest_git_blob_sha1") != _git_blob_id(previous_raw)
            or new.get("previous_manifest_path_count") != len(a)):
        raise RetentionHold("INCREMENT_PARENT_MANIFEST_MISMATCH")
    if not set(a) < set(b) or any(b[path] != row for path, row in a.items()):
        raise RetentionHold("INCREMENT_PREVIOUS_HISTORY_CHANGED")
    old_blobs, new_blobs = _index_by_blob(a), _index_by_blob(b)
    novel = set(new_blobs) - set(old_blobs)
    added = set(b) - set(a)
    if (new.get("incremental_added_paths") != len(added)
            or new.get("incremental_rehashed_unique_blobs") != len(novel)):
        raise RetentionHold("INCREMENT_DECLARED_COUNTS_MISMATCH")
    return old, new, a, b, added, novel


def _added_gzip(repo, base, head):
    if _git(repo, "merge-base", base, head, limit=64).strip().decode("ascii") != base:
        raise RetentionHold("INCREMENT_ANCESTRY_MISMATCH")
    data = _git(repo, "diff", "--no-ext-diff", "--no-renames", "--name-status",
                "-z", base, head, "--", limit=LIMIT).split(b"\0")
    if data[-1] != b"" or (len(data) - 1) % 2:
        raise RetentionHold("INCREMENT_DIFF_INVALID")
    result = set()
    for status, path in zip(data[0:-1:2], data[1:-1:2]):
        if not path.endswith(b".gz"):
            continue
        name = path.decode("ascii", "strict")
        if status != b"A" or not _path(name) or name in result:
            raise RetentionHold("INCREMENT_NONAPPEND_HISTORY")
        result.add(name)
    return result


def _identity(repo, commit, path):
    raw = _git(repo, "ls-tree", "-z", commit, "--", path, limit=4096)
    match = re.fullmatch(rb"100644 blob ([0-9a-f]{40})\t"
                         + re.escape(path.encode("ascii")) + rb"\0", raw)
    if not match:
        raise RetentionHold("INCREMENT_UNSAFE_TREE_ENTRY")
    oid = match.group(1).decode("ascii")
    size = int(_git(repo, "cat-file", "-s", oid, limit=64).strip())
    return oid, size


def inspect(repo, previous_raw, current_raw):
    repo = Path(repo)
    if not repo.is_dir() or repo.is_symlink():
        raise RetentionHold("INCREMENT_INVALID_LOCAL_REPO")
    old, new, a, b, added, novel = lineage(previous_raw, current_raw)
    base, before, after = (old["archive_bootstrap_sha"], old["source_main_sha"],
                           new["source_main_sha"])
    for sha in (base, before, after):
        if not _valid_sha(sha) or _git(repo, "cat-file", "-t", sha, limit=64).strip() != b"commit":
            raise RetentionHold("INCREMENT_PIN_NOT_COMMIT")
    if (_added_gzip(repo, base, before) != set(a)
            or _added_gzip(repo, before, after) != added
            or _added_gzip(repo, base, after) != set(b)):
        raise RetentionHold("INCREMENT_INCOMPLETE_ADDITION_SET")
    hashed = set()
    for path, row in sorted(b.items()):
        oid, size = row["git_blob_sha1"], row["compressed_bytes"]
        if _identity(repo, after, path) != (oid, size):
            raise RetentionHold("INCREMENT_NEW_TREE_MISMATCH")
        if path in a and _identity(repo, before, path) != (oid, size):
            raise RetentionHold("INCREMENT_OLD_TREE_MISMATCH")
        if oid in novel and oid not in hashed:
            if _blob(repo, after, path) != (oid, size, row["sha256_compressed"]):
                raise RetentionHold("INCREMENT_NEW_RAW_DIGEST_MISMATCH")
            hashed.add(oid)
    if hashed != novel:
        raise RetentionHold("INCREMENT_UNHASHED_NOVEL_BLOB")
    return {
        "status": "HOLD_INCREMENTAL_LOCAL_SOURCE_REVIEW_ONLY",
        "previous_paths": len(a), "current_paths": len(b),
        "new_paths": len(added), "new_unique_blobs_hashed": len(hashed),
        "inherited_sha256_rehashed": False,
        "previous_source_sha": before, "source_sha": after,
        "remote_archive_copy_confirmed": False,
        "independent_archive_retention_verified": False,
        "main_ruleset_activation_authorized": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        for p in (args.previous, args.current):
            if p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= LIMIT:
                raise RetentionHold("INCREMENT_UNSAFE_MANIFEST_FILE")
        receipt = inspect(args.repo, args.previous.read_bytes(), args.current.read_bytes())
    except (ValueError, OSError, TypeError, KeyError, RuntimeError):
        receipt = {"status": "HOLD_INCREMENT_UNVERIFIABLE",
                   "production_recommendations": "DISABLED"}
    print(json.dumps(receipt, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
