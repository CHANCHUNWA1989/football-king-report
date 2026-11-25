"""Pinned source archive byte inventory, offline Git only, no write authority."""
import argparse
import hashlib
import json
from pathlib import Path

from ops.history_blob_retention_preflight import _blob, _git, _unique, _valid_sha, _path, RetentionHold
from ops.incremental_history_manifest import _added_gzip


def verify(repo, manifest):
    if (type(manifest) is not dict
            or manifest.get("schema") != "football-king-pinned-history-tree-inventory-v1"
            or manifest.get("source_repo") != "CHANCHUNWA1989/football-king-report"
            or manifest.get("archive_write_authorized") is not False
            or manifest.get("remote_archive_copy_confirmed") is not False
            or manifest.get("production_recommendations") != "DISABLED"):
        raise RetentionHold("UNSAFE_TREE_INVENTORY")
    source, base = manifest["source_main_sha"], manifest["archive_bootstrap_sha"]
    if not all(_valid_sha(x) for x in (source, base)):
        raise RetentionHold("INVALID_PIN")
    for sha in (source, base):
        if _git(repo, "cat-file", "-t", sha, limit=64).strip() != b"commit":
            raise RetentionHold("PIN_NOT_COMMIT")
    rows = manifest["records"]
    if type(rows) is not list or not 1 <= len(rows) <= 256:
        raise RetentionHold("INVALID_RECORD_COUNT")
    seen, blobs, output = set(), {}, []
    for row in rows:
        path, oid, size = row["path"], row["git_blob_sha1"], row["compressed_bytes"]
        if not _path(path) or path in seen or not _valid_sha(oid) or type(size) is not int:
            raise RetentionHold("INVALID_TREE_RECORD")
        seen.add(path)
        actual = _blob(repo, source, path)
        if actual is None or actual[:2] != (oid, size):
            raise RetentionHold("SOURCE_BLOB_MISMATCH")
        # The Git blob ID is independently recalculated by Git from its bytes
        # using the Git blob header below; no object storage is modified.
        data = _git(repo, "cat-file", "blob", oid)
        if hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest() != oid:
            raise RetentionHold("SOURCE_BLOB_HASH_MISMATCH")
        digest = actual[2]
        if row["prior_sha256_compressed"] is not None and row["prior_sha256_compressed"] != digest:
            raise RetentionHold("PRIOR_SHA256_MISMATCH")
        if oid in blobs and blobs[oid] != digest:
            raise RetentionHold("CONFLICTING_BLOB_DIGEST")
        blobs[oid] = digest
        output.append(dict(path=path, git_blob_sha1=oid, compressed_bytes=size,
                           sha256_compressed=digest))
    if (_added_gzip(repo, base, source) != seen
            or manifest["history_added_count"] != len(seen)
            or manifest["unique_git_blobs"] != len(blobs)
            or manifest["compressed_bytes_sum"] != sum(row["compressed_bytes"] for row in output)):
        raise RetentionHold("INCOMPLETE_OR_INCONSISTENT_TREE_INVENTORY")
    return dict(status="HOLD_SOURCE_BYTES_REHASHED_READ_ONLY", source_sha=source,
                archive_bootstrap_sha=base, source_paths_rehashed=len(output),
                unique_blobs=len(blobs), source_sha256_records=output,
                remote_archive_copy_confirmed=False, archive_write_authorized=False,
                independent_archive_retention_verified=False,
                production_recommendations="DISABLED")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.manifest.is_symlink() or not 0 < args.manifest.stat().st_size <= 262144:
            raise RetentionHold("UNSAFE_MANIFEST")
        report = verify(args.repo, json.loads(args.manifest.read_bytes(), object_pairs_hook=_unique))
    except (ValueError, OSError, KeyError, TypeError, RuntimeError):
        print(json.dumps(dict(status="HOLD_SOURCE_BYTES_UNVERIFIABLE",
                              archive_write_authorized=False,
                              production_recommendations="DISABLED")))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
