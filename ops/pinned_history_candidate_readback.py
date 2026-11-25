"""Read-only exact 88-path migration candidate comparison. No hosted writes."""
import argparse
import json
from pathlib import Path
from ops.pinned_history_tree_rehash import verify
from ops.history_blob_retention_preflight import _blob, _git, _valid_sha, RetentionHold


def verify_candidate(repo, manifest, candidate):
    if not _valid_sha(candidate) or _git(repo, "cat-file", "-t", candidate, limit=64).strip() != b"commit":
        raise RetentionHold("INVALID_CANDIDATE_PIN")
    source = verify(repo, manifest)
    for row in source["source_sha256_records"]:
        expected = (row["git_blob_sha1"], row["compressed_bytes"], row["sha256_compressed"])
        if _blob(repo, candidate, row["path"]) != expected:
            raise RetentionHold("CANDIDATE_COMPRESSED_BLOB_MISMATCH")
    return dict(status="HOLD_CANDIDATE_HISTORY_BYTES_MATCH", candidate_sha=candidate,
                source_sha=source["source_sha"],
                candidate_paths_rehashed=source["source_paths_rehashed"],
                unique_blobs=source["unique_blobs"],
                remote_archive_copy_confirmed=False, source_switch_authorized=False,
                independent_archive_retention_verified=False,
                production_recommendations="DISABLED")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--candidate", required=True)
    args = p.parse_args()
    try:
        if args.manifest.is_symlink() or not 0 < args.manifest.stat().st_size <= 262144:
            raise RetentionHold("UNSAFE_MANIFEST")
        from ops.history_blob_retention_preflight import _unique
        report = verify_candidate(args.repo, json.loads(args.manifest.read_bytes(), object_pairs_hook=_unique), args.candidate)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError):
        print(json.dumps(dict(status="HOLD_CANDIDATE_HISTORY_BYTES_UNVERIFIED", production_recommendations="DISABLED", source_switch_authorized=False)))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
