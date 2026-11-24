"""Deterministic unsigned custody subject; never an external witness or write grant."""
import argparse
import hashlib
import json
from pathlib import Path

from ops.history_blob_retention_preflight import _blob, _git, _unique, _valid_sha, RetentionHold
from ops.pinned_history_tree_rehash import verify
from ops.thirteen_latest_reader_preflight import CONTRACTS, read_pinned, parse
from ops.six_latest_reader_preflight import SIX_LEAGUE_GROUP


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def delta(repo, base, head):
    if _git(repo, "merge-base", base, head, limit=64).strip().decode("ascii") != base:
        raise RetentionHold("CUSTODY_ANCESTRY_MISMATCH")
    raw = _git(repo, "diff", "--no-ext-diff", "--no-renames", "--name-status", "-z",
               base, head, "--", limit=262144).split(b"\0")
    if raw[-1] != b"" or (len(raw) - 1) % 2:
        raise RetentionHold("CUSTODY_DIFF_INVALID")
    result = {}
    for status, path in zip(raw[:-1:2], raw[1:-1:2]):
        name = path.decode("ascii", "strict")
        if name in result:
            raise RetentionHold("CUSTODY_DIFF_DUPLICATE")
        result[name] = status.decode("ascii")
    return result


def build(repo, manifest, candidate):
    if not _valid_sha(candidate) or _git(repo, "cat-file", "-t", candidate, limit=64).strip() != b"commit":
        raise RetentionHold("INVALID_CANDIDATE_PIN")
    evidence = verify(repo, manifest)
    source, base = evidence["source_sha"], evidence["archive_bootstrap_sha"]
    rows = sorted(evidence["source_sha256_records"], key=lambda r: r["path"])
    expected = {r["path"]: "A" for r in rows}
    if delta(repo, base, candidate) != expected:
        raise RetentionHold("CANDIDATE_HAS_UNEXPECTED_DELTA")
    if delta(repo, base, source) != dict(expected, **{p: "M" for p in CONTRACTS}):
        raise RetentionHold("SOURCE_HAS_UNREVIEWED_DELTA")
    for row in rows:
        if _blob(repo, candidate, row["path"]) != (
                row["git_blob_sha1"], row["compressed_bytes"], row["sha256_compressed"]):
            raise RetentionHold("CANDIDATE_HISTORY_BYTES_MISMATCH")
    pointers = []
    clocks = {"source": {}, "archive": {}}
    for path in sorted(CONTRACTS):
        old, old_oid = read_pinned(repo, base, path)
        new, new_oid = read_pinned(repo, source, path)
        copy, copy_oid = read_pinned(repo, candidate, path)
        ot, _, _ = parse(path, old)
        nt, _, _ = parse(path, new)
        if copy != old or copy_oid != old_oid or nt <= ot:
            raise RetentionHold("CUSTODY_POINTER_INVARIANT_FAILED")
        clocks["source"][path], clocks["archive"][path] = nt, ot
        pointers.append(dict(path=path, archive_blob_sha1=old_oid,
                             archive_sha256=hashlib.sha256(old).hexdigest(),
                             source_blob_sha1=new_oid,
                             source_sha256=hashlib.sha256(new).hexdigest()))
    if any(len({c[p] for p in SIX_LEAGUE_GROUP}) != 1 for c in clocks.values()):
        raise RetentionHold("SIX_LEAGUE_SNAPSHOT_SPLIT")
    subject = dict(schema="football-king-unsigned-archive-custody-subject-v1",
                   repository="CHANCHUNWA1989/football-king-report",
                   source_main_sha=source, archive_base_sha=base, archive_candidate_sha=candidate,
                   history_records=rows, mutable_pointer_records=pointers,
                   production_recommendations="DISABLED")
    return dict(status="HOLD_UNSIGNED_CUSTODY_SUBJECT_READY", subject=subject,
                subject_sha256=hashlib.sha256(canonical(subject)).hexdigest(),
                history_paths=len(rows), mutable_pointers=len(pointers),
                external_signature_verified=False, trusted_timestamp_verified=False,
                independent_archive_retention_verified=False,
                independent_review_verified=False, hosted_archive_write_authorized=False,
                source_switch_authorized=False, production_recommendations="DISABLED")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--candidate", required=True)
    args = p.parse_args()
    try:
        if args.manifest.is_symlink() or not 0 < args.manifest.stat().st_size <= 262144:
            raise RetentionHold("UNSAFE_MANIFEST")
        out = build(args.repo, json.loads(args.manifest.read_bytes(), object_pairs_hook=_unique), args.candidate)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError):
        print(json.dumps(dict(status="HOLD_UNSIGNED_SUBJECT_NOT_VERIFIABLE",
                              hosted_archive_write_authorized=False, production_recommendations="DISABLED")))
        return 1
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
