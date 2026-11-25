"""Public GitHub pinned snapshot observer (read only; no release authority).

Checks the exact source/target Git trees against the history manifest and
runs both actual mobile builders on one pinned real settlement document.
No authentication, redirects, archive writes, site publish or live feed use.
A completed observation is not a successful cutover.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib import error, request

from ops.history_blob_retention_preflight import _validate
from ops.mobile_settlement_parity_preflight import preflight
from ops.public_readiness_site import build as readiness

ROOT = "https://api.github.com/repos/CHANCHUNWA1989/football-king-report"
SHA = re.compile(r"[0-9a-f]{40}\Z")
TREE_LIMIT = 16 * 1024 * 1024
BLOB_LIMIT = 12 * 1024 * 1024
MANIFEST = Path("docs/P0_569_PINNED_35_HISTORY_BLOBS_SHA256_2026_11_24.json")
DOCS = ("evidence/settled.json", "sources/seven_quality_gates_latest.json",
        "market/latest.json")


class SnapshotHold(ValueError):
    """Fixed error, never reveal raw source data."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _pairs(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise SnapshotHold("DUPLICATE_SNAPSHOT_KEY")
        d[k] = v
    return d


def _decode(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          SnapshotHold("NONFINITE_SNAPSHOT_VALUE")))


def _get(endpoint, limit):
    if not re.fullmatch(r"/git/(?:commits/[0-9a-f]{40}|trees/[0-9a-f]{40}\?recursive=1|blobs/[0-9a-f]{40})", endpoint):
        raise SnapshotHold("SNAPSHOT_ENDPOINT_NOT_ALLOWED")
    req = request.Request(ROOT + endpoint, method="GET", headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "football-king-pinned-snapshot-observer",
    })
    with request.build_opener(NoRedirect).open(req, timeout=30) as resp:
        if resp.status != 200:
            raise SnapshotHold("SNAPSHOT_HTTP_FAILURE")
        raw = resp.read(limit + 1)
    if not 0 < len(raw) <= limit:
        raise SnapshotHold("SNAPSHOT_RESPONSE_LIMIT")
    doc = _decode(raw)
    if not isinstance(doc, dict):
        raise SnapshotHold("SNAPSHOT_RESPONSE_SHAPE")
    return doc


def _tree(commit_sha, get):
    if not isinstance(commit_sha, str) or not SHA.fullmatch(commit_sha):
        raise SnapshotHold("INVALID_SNAPSHOT_SHA")
    commit = get("/git/commits/" + commit_sha, 256 * 1024)
    if commit.get("sha") != commit_sha or not isinstance(commit.get("tree"), dict):
        raise SnapshotHold("SNAPSHOT_COMMIT_MISMATCH")
    tree_sha = commit["tree"].get("sha")
    if not isinstance(tree_sha, str) or not SHA.fullmatch(tree_sha):
        raise SnapshotHold("INVALID_SNAPSHOT_TREE_SHA")
    tree = get("/git/trees/" + tree_sha + "?recursive=1", TREE_LIMIT)
    if (tree.get("sha") != tree_sha or tree.get("truncated") is not False
            or not isinstance(tree.get("tree"), list)):
        raise SnapshotHold("SNAPSHOT_TREE_INCOMPLETE")
    rows = {}
    for row in tree["tree"]:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise SnapshotHold("SNAPSHOT_TREE_ENTRY_INVALID")
        if row["path"] in rows:
            raise SnapshotHold("SNAPSHOT_TREE_DUPLICATE_PATH")
        rows[row["path"]] = row
    return rows


def _identity(row):
    if (not isinstance(row, dict) or row.get("type") != "blob"
            or row.get("mode") != "100644" or type(row.get("size")) is not int
            or row["size"] <= 0 or not isinstance(row.get("sha"), str)
            or not SHA.fullmatch(row["sha"])):
        raise SnapshotHold("UNSAFE_SNAPSHOT_BLOB")
    return row["sha"], row["size"]


def compare_trees(manifest, source, target):
    entries = _validate(manifest)
    missing, different, matching = [], [], []
    for path, expected in sorted(entries.items()):
        identity = (expected["git_blob_sha1"], expected["compressed_bytes"])
        if _identity(source.get(path)) != identity:
            raise SnapshotHold("SOURCE_TREE_MANIFEST_MISMATCH")
        if path not in target:
            missing.append(path)
        else:
            try:
                same = _identity(target[path]) == identity
            except SnapshotHold:
                same = False
            (matching if same else different).append(path)
    return {
        "source_manifest_tree_entries_matched": len(entries),
        "target_git_blob_identity_matches": len(matching),
        "target_missing_paths": len(missing),
        "target_different_paths": len(different),
        "target_raw_sha256_readback_performed": False,
        "missing_paths": missing,
        "different_paths": different,
    }


def _read_document(tree, path, get):
    if path not in DOCS:
        raise SnapshotHold("SNAPSHOT_DOCUMENT_NOT_ALLOWED")
    oid, size = _identity(tree.get(path))
    if size > 8_000_000:
        raise SnapshotHold("SNAPSHOT_BLOB_TOO_LARGE")
    blob = get("/git/blobs/" + oid, BLOB_LIMIT)
    if blob.get("sha") != oid or blob.get("encoding") != "base64":
        raise SnapshotHold("SNAPSHOT_BLOB_RESPONSE_MISMATCH")
    if not isinstance(blob.get("content"), str):
        raise SnapshotHold("SNAPSHOT_BLOB_RESPONSE_MISMATCH")
    try:
        raw = base64.b64decode("".join(blob["content"].split()), validate=True)
    except (ValueError, TypeError) as exc:
        raise SnapshotHold("SNAPSHOT_BLOB_ENCODING_INVALID") from exc
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if len(raw) != size or actual != oid:
        raise SnapshotHold("SNAPSHOT_BLOB_CONTENT_MISMATCH")
    doc = _decode(raw)
    if not isinstance(doc, dict) or doc.get("production_recommendations") != "DISABLED":
        raise SnapshotHold("SNAPSHOT_DOCUMENT_NOT_RESEARCH_ONLY")
    return doc, hashlib.sha256(raw).hexdigest()


def observe(manifest, *, get=_get, now=None):
    _validate(manifest)
    source_sha = manifest["source_main_sha"]
    target_sha = manifest["archive_bootstrap_sha"]
    source = _tree(source_sha, get)
    target = _tree(target_sha, get)
    history = compare_trees(manifest, source, target)
    loaded = [_read_document(source, path, get) for path in DOCS]
    settled, gates, market = (x[0] for x in loaded)
    now = now or datetime.now(timezone.utc)
    parity = preflight(settled, settled, gates, market, now=now)
    public = readiness(settled, gates, market, now=now)
    return {
        "schema": "football-king-pinned-public-snapshot-observation-v1",
        "status": "HOLD_PINNED_PUBLIC_SNAPSHOT_OBSERVED_READ_ONLY",
        "source_sha": source_sha,
        "archive_snapshot_sha": target_sha,
        "checked_utc": now.isoformat(),
        "history": history,
        "settlement_sha256": loaded[0][1],
        "pinned_real_research_rows": parity["legacy_sample_count"],
        "official_readiness_rows_same_input": parity["candidate_public_readiness_count_if_switched"],
        "daily_scorecard_rows_same_input": parity["candidate_daily_scorecard_count"],
        "same_input_count_parity": parity["candidate_same_input_count_parity"],
        "independently_verified_result_cases": public["independently_verified_result_cases"],
        "quality_gates_passed": public["quality_gates_passed"],
        "quality_gates_total": public["quality_gates_total"],
        "market_snapshot_as_of_utc": market.get("as_of_utc"),
        "market_baseline_fresh": public["market_baseline_fresh"],
        "current_live_heads_attested_by_this_observer": False,
        "hosted_archive_retention_attested": False,
        "site_published": False,
        "source_switch_authorized": False,
        "production_recommendations": "DISABLED",
    }


# Only fixed reason codes authored by this observer are public-safe.
_PUBLIC_HOLD_REASONS = frozenset((
    "DUPLICATE_SNAPSHOT_KEY",
    "INVALID_SNAPSHOT_SHA",
    "INVALID_SNAPSHOT_TREE_SHA",
    "NONFINITE_SNAPSHOT_VALUE",
    "SNAPSHOT_BLOB_CONTENT_MISMATCH",
    "SNAPSHOT_BLOB_ENCODING_INVALID",
    "SNAPSHOT_BLOB_RESPONSE_MISMATCH",
    "SNAPSHOT_BLOB_TOO_LARGE",
    "SNAPSHOT_COMMIT_MISMATCH",
    "SNAPSHOT_DOCUMENT_NOT_ALLOWED",
    "SNAPSHOT_DOCUMENT_NOT_RESEARCH_ONLY",
    "SNAPSHOT_ENDPOINT_NOT_ALLOWED",
    "SNAPSHOT_HTTP_FAILURE",
    "SNAPSHOT_RESPONSE_LIMIT",
    "SNAPSHOT_RESPONSE_SHAPE",
    "SNAPSHOT_TREE_DUPLICATE_PATH",
    "SNAPSHOT_TREE_ENTRY_INVALID",
    "SNAPSHOT_TREE_INCOMPLETE",
    "SOURCE_TREE_MANIFEST_MISMATCH",
    "UNSAFE_PINNED_MANIFEST",
    "UNSAFE_SNAPSHOT_BLOB",
))


def _safe_failure_reason(exc):
    if isinstance(exc, SnapshotHold) and str(exc) in _PUBLIC_HOLD_REASONS:
        return str(exc)
    if isinstance(exc, error.HTTPError):
        if exc.code in (403, 429):
            return "SNAPSHOT_HTTP_ACCESS_OR_RATE_LIMIT"
        if exc.code == 404:
            return "SNAPSHOT_HTTP_NOT_FOUND"
        return "SNAPSHOT_HTTP_FAILURE"
    if isinstance(exc, OSError):
        return "SNAPSHOT_TRANSPORT_OR_IO_FAILURE"
    return "SNAPSHOT_VALIDATION_FAILED"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observe-only", required=True, action="store_true")
    parser.parse_args(argv)
    try:
        if MANIFEST.is_symlink() or not 0 < MANIFEST.stat().st_size <= 262144:
            raise SnapshotHold("UNSAFE_PINNED_MANIFEST")
        result = observe(_decode(MANIFEST.read_bytes()))
    except (ValueError, OSError, TypeError, KeyError, RuntimeError) as exc:
        print(json.dumps({"status": "HOLD_PINNED_PUBLIC_SNAPSHOT_UNVERIFIABLE",
                          "reason": _safe_failure_reason(exc),
                          "source_switch_authorized": False,
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    # Success means observation completed, never release or archive parity.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
