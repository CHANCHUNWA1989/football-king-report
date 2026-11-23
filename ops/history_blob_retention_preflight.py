"""Read-only local Git byte-retention verifier for a pinned history manifest.

Never fetches, checks out, copies, publishes or authorizes archive writes.
Git tree modes, raw gzip bytes and SHA-256 are checked independently of the
manifest's claimed counts. Even matching candidate bytes are offline evidence
only, not hosted custody, trusted timestamps, signatures or source truth.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from ops.archive_remote_ref_gate import sanitized_git_env

SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
PATH = re.compile(r"[A-Za-z0-9._/-]{1,280}\.gz\Z")
MAX_FILES = 256
MAX_BLOB = 8 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
SCHEMA = "football-king-history-binary-retention-manifest-v1"
REPO = "CHANCHUNWA1989/football-king-report"


class RetentionHold(ValueError):
    """Fixed error code, never a raw Git error or source payload."""


def _git(repo, *args, limit=MAX_BLOB):
    env = sanitized_git_env()
    env.update({"GIT_NO_LAZY_FETCH": "1", "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_ALLOW_PROTOCOL": ""})
    try:
        p = subprocess.run(
            ["git", "--no-replace-objects", "-c", "protocol.allow=never",
             "-C", str(repo), *args],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=20, env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RetentionHold("LOCAL_GIT_READ_FAILED") from exc
    if p.returncode or len(p.stdout) > limit:
        raise RetentionHold("LOCAL_GIT_READ_FAILED")
    return p.stdout


def _valid_sha(value, pattern=SHA):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _path(value):
    return (isinstance(value, str) and PATH.fullmatch(value) is not None
            and not value.startswith("/") and
            all(part not in ("", ".", "..", ".git") for part in value.split("/")))


def _unique(pairs):
    doc = {}
    for key, val in pairs:
        if key in doc:
            raise RetentionHold("DUPLICATE_MANIFEST_KEY")
        doc[key] = val
    return doc


def _validate(manifest):
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise RetentionHold("INVALID_HISTORY_MANIFEST")
    if (manifest.get("source_repo") != REPO
            or manifest.get("production_recommendations") != "DISABLED"
            or manifest.get("remote_archive_copy_confirmed") is not False
            or manifest.get("independent_archive_retention_verified") is not False
            or manifest.get("main_ruleset_activation_authorized") is not False
            or manifest.get("source_github_git_tree_truncated") is not False
            or manifest.get("digest_scope") != "raw_compressed_git_blob_bytes_not_decompressed_JSON"):
        raise RetentionHold("UNREVIEWED_HISTORY_MANIFEST")
    for field in ("source_main_sha", "archive_bootstrap_sha"):
        if not _valid_sha(manifest.get(field)):
            raise RetentionHold("INVALID_HISTORY_COMMIT")
    records = manifest.get("records")
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_FILES:
        raise RetentionHold("INVALID_HISTORY_RECORD_COUNT")
    by_path = {}
    for row in records:
        if not isinstance(row, dict):
            raise RetentionHold("INVALID_HISTORY_RECORD")
        path = row.get("path")
        size = row.get("compressed_bytes")
        if (not _path(path) or path in by_path
                or type(size) is not int or not 10 <= size <= MAX_BLOB
                or not _valid_sha(row.get("git_blob_sha1"))
                or not _valid_sha(row.get("sha256_compressed"), DIGEST)):
            raise RetentionHold("INVALID_HISTORY_RECORD")
        by_path[path] = row
    total = sum(row["compressed_bytes"] for row in records)
    if (total > MAX_TOTAL
            or manifest.get("source_added_gzip_paths") != len(records)
            or manifest.get("source_unique_git_blobs") != len({r["git_blob_sha1"] for r in records})
            or manifest.get("compressed_bytes_sum") != total):
        raise RetentionHold("HISTORY_MANIFEST_TOTAL_MISMATCH")
    return by_path


def _blob(repo, commit, path):
    # Exact tree entry; do not read the checkout (which may be dirty).
    raw = _git(repo, "ls-tree", "-z", commit, "--", path, limit=4096)
    if not raw:
        return None
    if raw.count(b"\0") != 1 or not raw.endswith(b"\0"):
        raise RetentionHold("AMBIGUOUS_HISTORY_TREE_ENTRY")
    metadata, sep, actual = raw[:-1].partition(b"\t")
    fields = metadata.split()
    if (not sep or actual != path.encode("ascii") or len(fields) != 3
            or fields[:2] != [b"100644", b"blob"]):
        raise RetentionHold("UNSAFE_HISTORY_TREE_ENTRY")
    oid = fields[2].decode("ascii")
    if not _valid_sha(oid):
        raise RetentionHold("INVALID_HISTORY_OBJECT")
    size = int(_git(repo, "cat-file", "-s", oid, limit=64).strip())
    if not 10 <= size <= MAX_BLOB:
        raise RetentionHold("HISTORY_BLOB_SIZE_LIMIT")
    data = _git(repo, "cat-file", "blob", oid)
    if len(data) != size or data[:3] != b"\x1f\x8b\x08":
        raise RetentionHold("INVALID_COMPRESSED_HISTORY_BLOB")
    return (oid, size, hashlib.sha256(data).hexdigest())


def inspect(repo, manifest, candidate_sha):
    """Verify manifest against source tree and compare a pinned local candidate."""
    repo = Path(repo)
    if not repo.is_dir() or repo.is_symlink() or not _valid_sha(candidate_sha):
        raise RetentionHold("INVALID_LOCAL_RETENTION_INPUT")
    entries = _validate(manifest)
    source, base = manifest["source_main_sha"], manifest["archive_bootstrap_sha"]
    for sha in (source, base, candidate_sha):
        if _git(repo, "cat-file", "-t", sha, limit=64).strip() != b"commit":
            raise RetentionHold("INVALID_HISTORY_COMMIT")
    # Require a complete exact gzip addition set, not a cherry-picked list.
    if _git(repo, "merge-base", base, source, limit=64).strip().decode() != base:
        raise RetentionHold("SOURCE_BOOTSTRAP_ANCESTRY_MISMATCH")
    diff = _git(repo, "diff", "--no-ext-diff", "--no-renames",
                "--name-status", "-z", base, source, "--", limit=262144)
    items = diff.split(b"\0")
    if items[-1] != b"" or (len(items)-1) % 2:
        raise RetentionHold("INVALID_HISTORY_DIFF")
    additions = set()
    for i in range(0, len(items)-1, 2):
        status, rawpath = items[i:i+2]
        if not rawpath.endswith(b".gz"):
            continue
        path = rawpath.decode("ascii", "strict")
        if status != b"A" or not _path(path):
            raise RetentionHold("SOURCE_HISTORY_MUTATED_OR_UNSAFE")
        additions.add(path)
    if additions != set(entries):
        raise RetentionHold("HISTORY_MANIFEST_INCOMPLETE_OR_EXTRA_PATH")
    if _git(repo, "merge-base", base, candidate_sha, limit=64).strip().decode() != base:
        raise RetentionHold("CANDIDATE_BOOTSTRAP_ANCESTRY_MISMATCH")
    missing, different = [], []
    for path, row in sorted(entries.items()):
        expected = (row["git_blob_sha1"], row["compressed_bytes"], row["sha256_compressed"])
        if _blob(repo, source, path) != expected:
            raise RetentionHold("SOURCE_HISTORY_MANIFEST_DIGEST_MISMATCH")
        candidate = _blob(repo, candidate_sha, path)
        if candidate is None:
            missing.append(path)
        elif candidate != expected:
            different.append(path)
    return {
        "status": "HOLD_LOCAL_HISTORY_RETENTION_REVIEW_ONLY",
        "source_sha": source,
        "candidate_sha": candidate_sha,
        "source_manifest_verified_files": len(entries),
        "candidate_exact_match_files": len(entries)-len(missing)-len(different),
        "missing_paths": missing,
        "different_paths": different,
        "local_candidate_bytes_match": not missing and not different,
        "remote_archive_copy_confirmed": False,
        "independent_archive_retention_verified": False,
        "main_ruleset_activation_authorized": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    args = parser.parse_args(argv)
    try:
        if args.manifest.is_symlink() or args.manifest.stat().st_size > 262144:
            raise RetentionHold("UNSAFE_HISTORY_MANIFEST")
        doc = json.loads(args.manifest.read_bytes(), object_pairs_hook=_unique)
        receipt = inspect(args.repo, doc, args.candidate_sha)
    except (ValueError, OSError, TypeError, RuntimeError):
        receipt = {"status": "HOLD_HISTORY_RETENTION_UNVERIFIABLE",
                   "independent_archive_retention_verified": False,
                   "production_recommendations": "DISABLED"}
    print(json.dumps(receipt, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
