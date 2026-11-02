"""Offline, private, byte-exact quote snapshot receipt (research only).

This is NOT an ingestion client. It never makes network calls, saves raw odds,
authenticates a publisher, authenticates the capture clock, or proves immutable
storage. SHA-256 plus replay detects mutation only when the original digest is
pinned *independently* in a trusted external system.

Keep the local source JSON and receipt OUT of public GitHub and public Pages.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat

from private_multi_market_audit import audit as audit_multi_market

SCHEMA = "football-king-private-raw-quote-receipt-v1"
PROVIDER = "the_odds_api_v4"
MAX_RAW_BYTES = 2_000_000
MARKETS = ("h2h", "spreads", "totals")
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class ReceiptError(ValueError):
    """Fixed public-safe reason. Never expose source content or credentials."""


def _reject(reason):
    raise ReceiptError(reason)


def _utc(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 80:
        _reject("INVALID_CAPTURE_UTC")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.utcoffset() != timedelta(0):
            _reject("NON_UTC_CAPTURE")
        return stamp.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError) as exc:
        raise ReceiptError("INVALID_CAPTURE_UTC") from exc


def _pairs_unique(pairs):
    result = {}
    for key, val in pairs:
        if key in result:
            _reject("DUPLICATE_JSON_KEY")
        result[key] = val
    return result


def _nonfinite(_):
    _reject("NONFINITE_JSON_NUMBER")


def _payload(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_RAW_BYTES:
        _reject("INVALID_RAW_RESPONSE_BYTES")
    try:
        payload = json.loads(raw, object_pairs_hook=_pairs_unique,
                             parse_constant=_nonfinite)
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, ReceiptError):
            raise
        raise ReceiptError("INVALID_JSON") from exc
    if not isinstance(payload, list) or len(payload) > 200:
        _reject("INVALID_ODDS_RESPONSE_EVENTS")
    return payload


def create_receipt(raw, captured_utc, *, expected_sha256=None):
    """Count-only digest of exact response bytes; no raw price is emitted.

    A caller-supplied expected digest is NOT an independently trusted anchor.
    To verify historical provenance an external signature/transparency log or
    protected append-only receipt archive must pin the digest separately.
    """
    stamp = _utc(captured_utc)
    payload = _payload(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        if type(expected_sha256) is not str or not DIGEST_PATTERN.fullmatch(expected_sha256):
            _reject("INVALID_EXPECTED_SHA256")
        if not hmac.compare_digest(digest, expected_sha256):
            _reject("RAW_SHA256_MISMATCH")
    try:
        report = audit_multi_market(payload, stamp)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise ReceiptError("PRIVATE_MARKET_AUDIT_FAILED") from exc
    counts = report["complete_prematch_bookmaker_lines_by_market"]
    if (report.get("production_recommendations") != "DISABLED"
            or any(type(counts.get(k)) is not int or counts[k] < 0 for k in MARKETS)):
        _reject("UNSAFE_PRIVATE_AUDIT")
    safe_counts = {k: counts[k] for k in MARKETS}
    return {
        "schema": SCHEMA,
        "provider_namespace": PROVIDER,
        "captured_utc_claimed_by_caller": stamp,
        "raw_response_sha256": digest,
        "raw_response_bytes": len(raw),
        "caller_supplied_expected_digest_matched": expected_sha256 is not None,
        "complete_prematch_bookmaker_lines_by_market": safe_counts,
        "missing_markets": [k for k in MARKETS if safe_counts[k] == 0],
        "rejection_counts_by_reason": report["rejections"],
        "events_matched": report["events_matched"],
        "status": "RESEARCH_ONLY" if any(safe_counts.values()) else "HOLD",
        "raw_response_bytes_exported": False,
        "individual_bookmaker_prices_exported": False,
        "publisher_independently_authenticated": False,
        "capture_clock_independently_authenticated": False,
        "digest_anchored_in_immutable_store": False,
        "executable_quote_verified": False,
        "independent_model_ev_verified": False,
        "formal_recommendations_enabled": False,
        "production_recommendations": "DISABLED",
    }


def verify_receipt(raw, receipt):
    """Recompute exact raw-byte digest and full count-only semantic audit."""
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        _reject("INVALID_RECEIPT")
    stamp = receipt.get("captured_utc_claimed_by_caller")
    anchor_matched = receipt.get("caller_supplied_expected_digest_matched")
    if type(anchor_matched) is not bool:
        _reject("INVALID_RECEIPT")
    digest = receipt.get("raw_response_sha256")
    if type(digest) is not str or not DIGEST_PATTERN.fullmatch(digest):
        _reject("INVALID_RECEIPT")
    if type(raw) is not bytes or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), digest):
        _reject("RAW_SHA256_MISMATCH")
    # Replaying a digest is not an independent validation of the original source.
    rebuilt = create_receipt(raw, stamp)
    rebuilt["caller_supplied_expected_digest_matched"] = anchor_matched
    if set(receipt) != set(rebuilt) or receipt != rebuilt:
        _reject("RECEIPT_REPLAY_MISMATCH")
    return {"schema": "football-king-private-quote-receipt-replay-v1",
            "bytes_and_semantics_replayed": True,
            "raw_response_sha256": digest,
            "publisher_independently_authenticated": False,
            "capture_clock_independently_authenticated": False,
            "digest_anchored_in_immutable_store": False,
            "eligible_for_model_promotion": False,
            "status": "HOLD", "production_recommendations": "DISABLED"}


def _read_raw_file(path):
    """Read only a bounded regular file, not a symlink or a directory."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RAW_BYTES:
                _reject("UNSAFE_INPUT_FILE")
            raw = source.read(MAX_RAW_BYTES + 1)
        if not 1 <= len(raw) <= MAX_RAW_BYTES:
            _reject("INVALID_RAW_RESPONSE_BYTES")
        return raw
    except (OSError, OverflowError) as exc:
        raise ReceiptError("UNSAFE_INPUT_FILE") from exc


def _write_private_new(path, report):
    """Owner-only, exclusive create; never overwrite source or existing proof."""
    data = (json.dumps(report, ensure_ascii=False, sort_keys=True,
                       allow_nan=False, indent=2) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(data)
    except OSError as exc:
        raise ReceiptError("UNSAFE_OR_EXISTING_RECEIPT_PATH") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--captured-utc")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--verify-receipt", type=Path,
                        help="Read existing private receipt and replay exact original bytes")
    args = parser.parse_args(argv)
    try:
        if args.verify_receipt is not None:
            if args.captured_utc is not None or args.expected_sha256 is not None:
                _reject("INCOMPATIBLE_VERIFY_OPTIONS")
            receipt = _payload_receipt(_read_raw_file(args.verify_receipt))
            result = verify_receipt(_read_raw_file(args.input), receipt)
        else:
            if args.captured_utc is None:
                _reject("CAPTURE_TIME_REQUIRED")
            result = create_receipt(_read_raw_file(args.input), args.captured_utc,
                                    expected_sha256=args.expected_sha256)
        _write_private_new(args.output, result)
    except ReceiptError as exc:
        # Error codes only. No private price, filename or source content.
        print(json.dumps({"status": "HOLD", "reason": str(exc),
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps({"status": result["status"], "receipt_created": True,
                      "production_recommendations": "DISABLED"}))
    return 0


def _payload_receipt(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_pairs_unique, parse_constant=_nonfinite)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        if isinstance(exc, ReceiptError):
            raise
        raise ReceiptError("INVALID_RECEIPT") from exc
    if not isinstance(value, dict):
        _reject("INVALID_RECEIPT")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
