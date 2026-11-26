"""Offline end-to-end private first-case replay and RFC3161 local preflight.

Requires original SHA-pinned private response pack, unchanged model/quote/
manifest originals, and an RFC3161 token over the EXACT manifest. Rebuilds the
same-response h2h selection from original provider bytes. Every result remains
HOLD: operator-supplied CA, unverified source origin, executable price, FT,
TSA policy and calibrated model are not independently authenticated here.

Never calls providers, retrieves credentials, rewrites originals or publishes
selected odds, bookmaker identities, fixture names or probabilities.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from ops import private_response_capture as capture
from first_case_payload_binding import (
    FORECAST_KEYS, FORECAST_SCHEMA, QUOTE_KEYS, QUOTE_SCHEMA,
    MANIFEST_KEYS, MANIFEST_SCHEMA, _read_json, _time,
)
from first_case_private_quote_link import build as reconstruct
from first_case_rfc3161_link import check as verify_token

SCHEMA = "football-king-first-case-private-end-to-end-audit-v1"
FILE_LIMIT = 1_000_000


class CaseAuditError(ValueError):
    pass


def _reject(code):
    raise CaseAuditError(code)


def _report(reason, *, pack_verified=False, raw_match=False, token_ok=False,
            manifest_sha=None):
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": reason,
        "private_original_pack_replayed": pack_verified,
        "exact_original_quote_and_manifest_reconstructed": raw_match,
        "local_rfc3161_manifest_signature_and_imprint_checked": token_ok,
        "manifest_sha256": manifest_sha,
        "tsa_trust_policy_verified": False,
        "forecast_origin_independently_authenticated": False,
        "source_capture_time_independently_authenticated": False,
        "bookmaker_quote_executable_authenticated": False,
        "independent_second_ft_source_authenticated": False,
        "regulation_ft_settlement_authenticated": False,
        "certified_forward_case_count": 0,
        "eligible_for_model_scoring": False,
        "positive_ev_verified": False,
        "model_promotion_allowed": False,
        "recommended_stake": None,
        "production_recommendations": "DISABLED",
    }


def _private_originals(forecast_path, quote_path, manifest_path):
    files = [Path(x) for x in (forecast_path, quote_path, manifest_path)]
    if (len(set(files)) != 3 or
            len({str(path.parent) for path in files}) != 1 or
            any(path.name in ("", ".", "..") or path.is_symlink() for path in files)):
        _reject("PRIVATE_CASE_FILES_NOT_DISTINCT_OR_SAME_DIRECTORY")
    parent = capture._path(files[0].parent)
    descriptor = capture._open_chain(parent)
    try:
        capture._directory_mode(descriptor)
        payloads = tuple(capture._read(descriptor, path.name, FILE_LIMIT)
                         for path in files)
    finally:
        os.close(descriptor)
    return payloads


def inspect(private_dir, forecast_path, quote_path, manifest_path, *,
            source_sha, run_id, attempt, expected_manifest_sha256,
            token_path, ca_path, openssl="openssl", now=None):
    """Recheck all source originals and live local signature before any credit."""
    when = datetime.now(timezone.utc) if now is None else now
    if type(when) is not datetime or when.tzinfo is None or when.utcoffset() is None:
        return _report("INVALID_AUDIT_CLOCK")
    when = when.astimezone(timezone.utc)
    try:
        forecast, quote, manifest = _private_originals(
            forecast_path, quote_path, manifest_path)
        quote_obj = _read_json(quote, QUOTE_KEYS, QUOTE_SCHEMA)
        manifest_obj = _read_json(manifest, MANIFEST_KEYS, MANIFEST_SCHEMA)
        _read_json(forecast, FORECAST_KEYS, FORECAST_SCHEMA)

        # Never trust the context captured in an operator-supplied quote:
        # source pack must independently be replayable from its original SHA.
        if (type(expected_manifest_sha256) is not str or
                len(expected_manifest_sha256) != 64 or
                any(ch not in "0123456789abcdef" for ch in expected_manifest_sha256)):
            _reject("INVALID_PRIVATE_PACK_SHA_PIN")
        provider = quote_obj.get("provider")
        if type(provider) is not str:
            _reject("INVALID_PINNED_PROVIDER_SCOPE")
        parts = provider.split("/")
        if (len(parts) != 3 or parts[0] != "the_odds_api_v4"
                or parts[2] != expected_manifest_sha256):
            _reject("ORIGINAL_PRIVATE_PACK_NOT_PINNED_IN_QUOTE")
        bookmaker = parts[1]
        selected = quote_obj["selection"]
        if selected not in ("HOME", "DRAW", "AWAY") or quote_obj["market"] != "h2h":
            _reject("PRIVATE_REPLAY_ONLY_SUPPORTS_H2H")

        # Private pack internal file permissions, receipt hashes, run identity,
        # every original raw response and manifest are checked by replay_records.
        records = capture.replay_records(
            private_dir, source_sha=source_sha, run_id=run_id, attempt=attempt,
            expected_manifest_sha256=expected_manifest_sha256)
        captured_at = _time(manifest_obj["created_utc"])
        # Recreate the original market selection AT ITS RECORDED SEAL TIME.
        # Do not replay against audit-now: after kickoff the quote is expected
        # to be stale, yet genuine historical evidence must remain replayable.
        expected_quote, expected_manifest, _ = reconstruct(
            forecast, records, pack_sha256=expected_manifest_sha256,
            bookmaker_id=bookmaker, selection=selected, now=captured_at)
        if expected_quote != quote:
            _reject("SELECTED_QUOTE_DIFFERENT_FROM_ORIGINAL_RAW_RESPONSE")
        if expected_manifest != manifest:
            _reject("SEALED_MANIFEST_DIFFERENT_FROM_SOURCE_RECONSTRUCTION")

        # The original manifest is now frozen in memory; OpenSSL hashes
        # precisely these bytes, not an operator-replaceable file path.
        token_result = verify_token(
            forecast, quote, manifest, token_path=token_path,
            ca_path=ca_path, openssl=openssl)
        if not token_result.get("local_openssl_signature_and_imprint_checked"):
            _reject("RFC3161_MANIFEST_LINK_OR_LOCAL_SIGNATURE_FAILED")
        signed = _time(token_result["tsa_gen_time_utc_claim"])
        if signed > when:
            _reject("TSA_TOKEN_SIGNED_AFTER_AUDIT_CLOCK")
        # Catch post-read modification to the individual evidence files or
        # private capture source pack. These checks do not prevent a privileged
        # attacker changing an external TSA authority or capture server.
        if _private_originals(forecast_path, quote_path, manifest_path) != (
                forecast, quote, manifest):
            _reject("PRIVATE_ORIGINAL_CHANGED_DURING_REPLAY")
        replay_again = capture.replay_records(
            private_dir, source_sha=source_sha, run_id=run_id, attempt=attempt,
            expected_manifest_sha256=expected_manifest_sha256)
        if replay_again != records:
            _reject("PRIVATE_PACK_CHANGED_DURING_REPLAY")
        return _report(
            "ORIGINAL_PACK_AND_LOCAL_TIMESTAMP_REPLAY_PASS_EXTERNAL_TRUST_STILL_MISSING",
            pack_verified=True, raw_match=True, token_ok=True,
            manifest_sha=hashlib.sha256(manifest).hexdigest())
    except CaseAuditError as exc:
        return _report(str(exc))
    except (ValueError, TypeError, OSError, OverflowError, KeyError,
            RecursionError) as exc:
        # Source-specific exception details may include private data and file
        # paths; keep only a public-safe fixed error, never echo raw payloads.
        return _report("PRIVATE_SOURCE_OR_TIMESTAMP_EVIDENCE_REJECTED")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "private-dir", "forecast", "quote", "manifest",
        "source-sha", "run-id", "attempt", "expected-manifest-sha256",
        "token", "ca",
    ):
        parser.add_argument("--"+name, required=True)
    args = parser.parse_args(argv)
    result = inspect(
        args.private_dir, args.forecast, args.quote, args.manifest,
        source_sha=args.source_sha, run_id=args.run_id, attempt=args.attempt,
        expected_manifest_sha256=args.expected_manifest_sha256,
        token_path=args.token, ca_path=args.ca)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    if not result.get("local_rfc3161_manifest_signature_and_imprint_checked"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
