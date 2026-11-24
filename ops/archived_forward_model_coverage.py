"""Inspect exact, Git-blob-pinned *compressed* real forward research archives.

Offline SHA/JSON/shape checks only. No source legitimacy, production timestamp,
model performance, OOS or bookmaker quote can be authenticated by this tool.
Even valid archives are always HOLD / DISABLED.
"""
import argparse
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat

SCHEMA = "football-king-forward-pair-original-coverage-v1"
MANIFEST_SCHEMA = "football-king-pinned-forward-pair-day-v1"
MAX_FILES = 20
MAX_GZ = 600_000
MAX_DECODED = 8_000_000
MAX_ROWS = 3000
PAIRS = ("model", "market")
AB = "probability-shrink-to-uniform-fixed-0.15-v1"
C = "market-anchored-fixed-25pct-model-75pct-consensus-v1"


def _hold(reason, **data):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False, "model_promoted": False,
        "validated_penaltyblog_pre_match_pairs": 0,
        "certified_prospective_samples": 0,
        "publisher_identity_verified": False,
        "external_timestamp_verified": False,
        "result_truth_verified": False,
        "bookmaker_quote_executable_verified": False,
        **data,
    }


def _unique(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("DUPLICATE_JSON_KEY")
        d[k] = v
    return d


def _finite(_):
    raise ValueError("NONFINITE_NUMBER")


def _p3(v):
    return (type(v) is list and len(v) == 3 and
            all(type(x) in (float, int) and math.isfinite(x)
                and 0 <= x <= 1 for x in v)
            and abs(sum(v) - 1) <= 0.002)


def _read_checked_file(path, *, limit):
    if any(x.is_symlink() for x in (path, *path.parents)):
        raise ValueError("SYMLINK_ARCHIVE_NOT_ALLOWED")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 < info.st_size <= limit):
            raise ValueError("UNSAFE_ARCHIVE_FILE_OR_SIZE")
        raw = b""
        while len(raw) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw += part
        if len(raw) != info.st_size:
            raise ValueError("ARCHIVE_CHANGED_DURING_READ")
        return raw
    finally:
        os.close(fd)


def _git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()


def audit_day(manifest_bytes, root):
    """Verify immutable compressed local bytes and count research shapes only."""
    try:
        if type(manifest_bytes) is not bytes or not 0 < len(manifest_bytes) <= 20000:
            raise ValueError("INVALID_MANIFEST_BYTES")
        manifest = json.loads(manifest_bytes, object_pairs_hook=_unique,
                              parse_constant=_finite)
        if (type(manifest) is not dict or
                set(manifest) != {"schema", "source_commit", "day", "files",
                                  "production_recommendations"} or
                manifest["schema"] != MANIFEST_SCHEMA or
                manifest["production_recommendations"] != "DISABLED" or
                not re.fullmatch(r"[0-9a-f]{40}", manifest["source_commit"]) or
                not re.fullmatch(r"20[0-9]{2}/(0[1-9]|1[0-2])/[0-3][0-9]",
                                 manifest["day"])):
            raise ValueError("INVALID_ARCHIVE_MANIFEST")
        day = manifest["day"]
        parts = day.split("/")
        from datetime import date
        date(*(int(v) for v in parts))
        entries = manifest["files"]
        if type(entries) is not list or not 1 <= len(entries) <= MAX_FILES:
            raise ValueError("INVALID_ARCHIVE_FILE_LIST")
        root = Path(root)
        seen = set()
        totals = {
            "archived_comparison_rows_unverified": 0,
            "legacy_A_model_vector_candidates_unverified": 0,
            "market_probability_vectors_unverified": 0,
            "legacy_AB_shrinkage_candidates_not_penaltyblog": 0,
            "legacy_C_market_anchor_candidates_not_penaltyblog": 0,
            "native_penaltyblog_model_outputs_observed": 0,
        }
        for entry in entries:
            if (type(entry) is not dict or set(entry) != {"filename", "size_bytes",
                                                        "git_blob_sha1"}):
                raise ValueError("INVALID_FILE_PIN")
            name = entry["filename"]
            if (type(name) is not str or
                    not re.fullmatch(r"[1-9][0-9]{5,19}-[1-9][0-9]{0,9}\.json\.gz", name)
                    or name in seen):
                raise ValueError("INVALID_OR_DUPLICATE_ARCHIVE_NAME")
            seen.add(name)
            if (type(entry["size_bytes"]) is not int or
                    not 0 < entry["size_bytes"] <= MAX_GZ or
                    type(entry["git_blob_sha1"]) is not str or
                    re.fullmatch(r"[0-9a-f]{40}", entry["git_blob_sha1"]) is None):
                raise ValueError("INVALID_FILE_PIN")
            path = root / day / name
            raw = _read_checked_file(path, limit=MAX_GZ)
            if (len(raw) != entry["size_bytes"] or
                    _git_blob(raw) != entry["git_blob_sha1"]):
                raise ValueError("PINNED_ARCHIVE_GIT_BLOB_MISMATCH")
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as stream:
                    decompressed = stream.read(MAX_DECODED + 1)
                if not 0 < len(decompressed) <= MAX_DECODED:
                    raise ValueError("ARCHIVE_EXPANSION_LIMIT")
                payload = json.loads(decompressed, object_pairs_hook=_unique,
                                     parse_constant=_finite)
            except (OSError, EOFError, UnicodeError) as exc:
                raise ValueError("INVALID_ARCHIVED_GZIP_OR_JSON") from exc
            if (type(payload) is not dict or
                    payload.get("production_recommendations") != "DISABLED" or
                    type(payload.get("comparisons")) is not list or
                    len(payload["comparisons"]) > MAX_ROWS):
                raise ValueError("INVALID_OR_UNSAFE_ARCHIVED_BATCH")
            for row in payload["comparisons"]:
                if type(row) is not dict or row.get("production_recommendations") != "DISABLED":
                    raise ValueError("INVALID_OR_UNSAFE_ARCHIVED_ROW")
                totals["archived_comparison_rows_unverified"] += 1
                if "model" in row:
                    if not _p3(row["model"]):
                        raise ValueError("INVALID_LEGACY_MODEL_VECTOR")
                    totals["legacy_A_model_vector_candidates_unverified"] += 1
                if "market" in row:
                    if not _p3(row["market"]):
                        raise ValueError("INVALID_LEGACY_MARKET_VECTOR")
                    totals["market_probability_vectors_unverified"] += 1
                for key, label, counter in (
                    ("ab", AB, "legacy_AB_shrinkage_candidates_not_penaltyblog"),
                    ("c", C, "legacy_C_market_anchor_candidates_not_penaltyblog"),
                ):
                    if key in row or key + "_model" in row:
                        if not _p3(row.get(key)) or row.get(key + "_model") != label:
                            raise ValueError("UNKNOWN_OR_SPOOFED_CHALLENGER")
                        totals[counter] += 1
                if any("penaltyblog" in k.lower() for k in row.keys()):
                    # External dependency outputs must arrive in separate
                    # provenance-checked files, never by adding a new field
                    # into a historical A/B/C capture.
                    raise ValueError("LEGACY_ARCHIVE_PENALTYBLOG_FIELD_INJECTION")
        return _hold(
            "ORIGINAL_FORWARD_ARCHIVES_OBSERVED_PENALTYBLOG_PAIR_NOT_PRESENT",
            source_commit_reference_unattested=manifest["source_commit"],
            checked_day=day, pinned_archive_files=len(entries),
            pinned_git_blob_bytes_consistent=True,
            **totals,
            note=("Git blob pinning authenticates relative archive bytes only; "
                  "the archived A, AB and C research labels cannot be "
                  "reclassified as an independently timed Penaltyblog refit."),
        )
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        reason = str(exc)
        return _hold(reason if len(reason) < 110 else "ARCHIVE_PREFLIGHT_REJECTED")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Research-only historic forward archive audit")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--archives", required=True)
    args = parser.parse_args(argv)
    try:
        manifest = _read_checked_file(Path(args.manifest), limit=20000)
        result = audit_day(manifest, args.archives)
    except (OSError, ValueError) as exc:
        result = _hold(str(exc) if len(str(exc)) < 110 else "MANIFEST_UNREADABLE")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("pinned_git_blob_bytes_consistent") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
