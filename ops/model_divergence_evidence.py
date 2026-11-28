"""Offline evidence byte integrity; not provider authentication or xG derivation."""
import hashlib
import json
import math
from ops.model_divergence_binding import compare, _HEX
from ops.model_divergence_batch import MAX_FIXTURES

MAX_DOCUMENT = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


def _digest(data, expected):
    if (type(data) is not bytes or not 0 < len(data) <= MAX_DOCUMENT
            or type(expected) is not str or not _HEX.fullmatch(expected)
            or hashlib.sha256(data).hexdigest() != expected):
        raise ValueError("BYTE_DIGEST_MISMATCH")


def _unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("DUPLICATE_JSON_KEY")
        out[k] = v
    return out


def _finite(value):
    f = float(value)
    if not math.isfinite(f):
        raise ValueError("NONFINITE_JSON")
    return f


def _reject(value):
    raise ValueError("NONFINITE_JSON")


def _rows(document, expected, raw):
    _digest(document, expected)
    rows = json.loads(document.decode("utf-8"), object_pairs_hook=_unique,
                      parse_constant=_reject, parse_float=_finite)
    if type(rows) is not list or len(rows) > MAX_FIXTURES:
        raise ValueError("INVALID_PROJECTION")
    used = set()
    for row in rows:
        if type(row) is not dict:
            raise ValueError("INVALID_ROW")
        digest = row["source_sha256"]
        if type(digest) is not str or not _HEX.fullmatch(digest):
            raise ValueError("INVALID_RAW_DIGEST")
        used.add(digest)
    if used != set(raw):
        raise ValueError("MISSING_OR_UNUSED_RAW_BYTES")
    for digest in used:
        _digest(raw[digest], digest)
    return rows


def evaluate_evidence(manifest, left_document, right_document, *,
                      left_sha256, right_sha256, left_raw, right_raw,
                      left_provider, right_provider, left_model, right_model,
                      as_of_utc):
    """Compare only parsed bytes matching caller-pinned digests.

    Raw provider payloads are opaque: matching hashes do NOT prove that the
    normalized forecast was derived from them, that they came from a provider,
    or that the asserted collection time is authentic. No bytes are returned.
    """
    flags = dict(source_authenticated=False, source_bytes_verified=False,
                 native_identity_authenticated=False, model_calibrated=False,
                 normalized_documents_hash_match=False,
                 raw_payload_hashes_match=False, raw_payload_count=0,
                 model_input_derivation_verified=False,
                 production_recommendations="DISABLED", can_recommend_bets=False)
    blocked = dict(status="HOLD", reason="INVALID_EVIDENCE_BYTES",
                   results=[], counts={}, **flags)
    try:
        total = 0
        for doc in (left_document, right_document):
            if type(doc) is not bytes or not 0 < len(doc) <= MAX_DOCUMENT:
                raise ValueError("INVALID_DOCUMENT")
            total += len(doc)
        for raw in (left_raw, right_raw):
            if type(raw) is not dict or len(raw) > MAX_FIXTURES:
                raise ValueError("INVALID_RAW_MAP")
            for digest, data in raw.items():
                if (type(digest) is not str or not _HEX.fullmatch(digest)
                        or type(data) is not bytes or not 0 < len(data) <= MAX_DOCUMENT):
                    raise ValueError("INVALID_RAW_ENTRY")
                total += len(data)
                if total > MAX_TOTAL_BYTES:
                    raise ValueError("BYTE_BUDGET")
        left = _rows(left_document, left_sha256, left_raw)
        right = _rows(right_document, right_sha256, right_raw)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return blocked
    result = compare(manifest, left, right, left_provider=left_provider,
                     right_provider=right_provider, left_model=left_model,
                     right_model=right_model, as_of_utc=as_of_utc)
    n = len(left_raw) + len(right_raw)
    return {**result, **flags, "normalized_documents_hash_match": True,
            "raw_payload_hashes_match": n > 0, "raw_payload_count": n}
