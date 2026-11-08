"""Authorized OFFLINE decrypt/replay for the first frozen dual result-source archive.

Requires a PRIVATE local age-PQ identity held ONLY by its owner. No identity is
stored, printed, uploaded to GitHub or used in routine CI. Exact 2026-11-08
public custody is verified BEFORE decryption; after age authenticates, the
original compressed envelope and decompressed provider bytes must match all
original, independently pinned receipt hashes and schema.

This is BYTE PRESERVATION proof only, never upstream/official FT authentication,
market evidence, actual kickoff verification, prediction accuracy, or bets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zlib

from ops.identity_ab_forward_seal import _date as parse_utc
from ops.identity_ab_two_source_custody import (
    SCHEMA, MAGIC, MAX_PACK_BYTES, MAX_ENVELOPE_HEADER, COMPRESSION, YEAR,
    TWO_SOURCES,
)
from ops.identity_ab_two_source_public_cipher_audit import (
    verify as verify_public,
    _read, _parse, INDEX_KEYS, RECEIPT_KEYS,
    SourceArchiveError, _digest as sha256,
)
from ops.identity_ab_sealed_archive_audit import MAX_INDEX_BYTES
from ops.private_response_relay import (
    _read as private_read, _crypto as crypto, RelayError,
)
from ops.private_response_capture import CaptureError
from ops.shadow_raw_source_collector import (
    MAX_BYTES, source_urls, validate_json_body, allowed_media_types,
    FetchValidationError,
)

REPORT_SCHEMA = "football-king-authorized-two-source-decrypt-replay-v1"
MANIFEST_KEYS = frozenset((
    "schema","provider","request_url","final_url","http_status",
    "content_type","received_utc","raw_sha256","raw_bytes",
    "compression","source_publisher_authenticated",
    "upstream_independence_authenticated","actual_kickoff_authenticated",
    "regulation_ft_authenticated","production_recommendations",
))
SECRET_LINE = re.compile(r"AGE-SECRET-KEY-PQ-1[A-Z0-9]{40,4096}\Z")


class AuthorizedReplayError(ValueError):
    """Safe fixed failure code; never expose key, filename or raw source bytes."""


def _require(ok, code):
    if not ok:
        raise AuthorizedReplayError(code)


def _secret(path):
    """Owner's secret file must live in a secure private directory, mode 0600."""
    try:
        raw=private_read(Path(path),8192,private=True)
        secret=raw.decode("ascii")
        lines=[line for line in secret.splitlines()
               if line and not line.startswith("#")]
        _require(len(lines)==1 and SECRET_LINE.fullmatch(lines[0]) is not None,
                 "PRIVATE_AGE_IDENTITY_INVALID")
        return (lines[0]+"\n").encode("ascii")
    except (RelayError,CaptureError,OSError,UnicodeError):
        raise AuthorizedReplayError("PRIVATE_AGE_IDENTITY_UNAVAILABLE") from None


def _unpack_authenticated(packed, *, provider, receipt):
    _require(type(packed) is bytes and 0<len(packed)<=MAX_PACK_BYTES
             and len(packed)==receipt["compressed_original_pack_bytes"]
             and sha256(packed)==receipt["compressed_original_pack_sha256"],
             "DECRYPTED_COMPRESSED_ENVELOPE_PIN_MISMATCH")
    n=len(MAGIC)
    _require(packed.startswith(MAGIC) and len(packed)>n+4,
             "INVALID_DECRYPTED_ENVELOPE_MAGIC")
    size=int.from_bytes(packed[n:n+4],"big")
    _require(0<size<=MAX_ENVELOPE_HEADER and n+4+size<len(packed),
             "INVALID_DECRYPTED_ENVELOPE_LENGTH")
    header_raw=packed[n+4:n+4+size]
    manifest=_parse(header_raw,expected=MANIFEST_KEYS)
    # Preserve exact original canonical manifest representation, not just
    # an equivalent semantic JSON document.
    expected_json=(json.dumps(manifest,ensure_ascii=False,sort_keys=True,
                              separators=(",",":"),allow_nan=False)+"\n").encode("utf-8")
    _require(header_raw==expected_json,
             "DECRYPTED_ENVELOPE_HEADER_NOT_CANONICAL")
    expected_url=source_urls(YEAR)[provider]
    # Validate fixed original source metadata and every FALSE authority flag.
    _require(manifest["schema"]==SCHEMA
             and manifest["provider"]==provider
             and manifest["request_url"]==expected_url
             and manifest["final_url"]==expected_url
             and type(manifest["http_status"]) is int
             and manifest["http_status"]==200
             and type(manifest["content_type"]) is str
             and manifest["content_type"] in allowed_media_types(provider)
             and manifest["received_utc"]==receipt["source_received_utc"]
             and manifest["raw_sha256"]==receipt["source_raw_sha256"]
             and type(manifest["raw_bytes"]) is int
             and manifest["raw_bytes"]==receipt["source_raw_bytes"]
             and manifest["compression"]==COMPRESSION
             and manifest["source_publisher_authenticated"] is False
             and manifest["upstream_independence_authenticated"] is False
             and manifest["actual_kickoff_authenticated"] is False
             and manifest["regulation_ft_authenticated"] is False
             and manifest["production_recommendations"]=="DISABLED",
             "DECRYPTED_SOURCE_HEADER_CONTRADICTION")
    try:
        parse_utc(manifest["received_utc"])
    except (ValueError,TypeError,OverflowError):
        raise AuthorizedReplayError("DECRYPTED_SOURCE_RECEIPT_TIME_INVALID") from None
    compressed=packed[n+4+size:]
    try:
        decompressor=zlib.decompressobj()
        original=decompressor.decompress(compressed,MAX_BYTES+1)
        _require(len(original)<=MAX_BYTES and decompressor.eof
                 and decompressor.unconsumed_tail==b""
                 and decompressor.unused_data==b"",
                 "DECRYPTED_SOURCE_DECOMPRESSION_UNSAFE")
        _require(decompressor.flush()==b"",
                 "DECRYPTED_SOURCE_DECOMPRESSION_UNSAFE")
    except zlib.error:
        raise AuthorizedReplayError("DECRYPTED_SOURCE_DECOMPRESSION_UNSAFE") from None
    _require(len(original)==receipt["source_raw_bytes"]
             and sha256(original)==receipt["source_raw_sha256"],
             "DECRYPTED_ORIGINAL_BYTE_SHA_MISMATCH")
    try:
        validate_json_body(original,provider)
    except (FetchValidationError,UnicodeError,ValueError,TypeError,RecursionError):
        raise AuthorizedReplayError("DECRYPTED_ORIGINAL_SOURCE_JSON_INVALID") from None
    return {
        "source_raw_bytes":len(original),
        "source_raw_sha256":sha256(original),
        "packed_sha256":sha256(packed),
        "provider_source_schema_valid":True,
    }


def replay(directory, *, identity_path, age_binary):
    """No network, no files written, decrypt strictly in memory after pins."""
    pinned=verify_public(directory)
    _require(pinned["public_source_ciphertext_integrity_verified"] is True
             and pinned["verified_public_files"]>=5
             and pinned["private_decryption_verified"] is False
             and pinned["certified_scored_case_count"]==0,
             "UNTRUSTED_CUSTODY_FOR_DECRYPTION")
    root=Path(directory)
    ix=_parse(_read(root,"index.json",MAX_INDEX_BYTES),expected=INDEX_KEYS)
    secret=_secret(identity_path)
    results={}
    for provider in TWO_SOURCES:
        meta=ix["sources"][provider]
        receipt=_parse(_read(root,meta["receipt_file"],8192),
                       expected=RECEIPT_KEYS)
        ciphertext=b"".join(_read(root,name,48_000)
                            for name in meta["parts"])
        _require(sha256(ciphertext)==receipt["encrypted_ciphertext_sha256"],
                 "ENCRYPTED_SOURCE_SHA_CHANGED_AFTER_PRECHECK")
        try:
            raw_pack=crypto(ciphertext,["--decrypt"],Path(age_binary),
                            identity=secret,maximum=MAX_PACK_BYTES)
        except (RelayError,CaptureError,ValueError,OSError,TimeoutError):
            raise AuthorizedReplayError("PQ_AGE_DECRYPTION_FAILED") from None
        results[provider]=_unpack_authenticated(
            raw_pack,provider=provider,receipt=receipt)
    _require(set(results)==set(TWO_SOURCES),
             "INCOMPLETE_ORIGINAL_SOURCE_REPLAY")
    return {
        "schema":REPORT_SCHEMA,
        "status":"HOLD",
        "public_ciphertext_integrity_verified":True,
        "original_source_bytes_decrypted_and_replayed":True,
        "sources_verified":len(results),
        "source_byte_proofs":results,
        "private_identity_disclosed_or_uploaded":False,
        "source_publisher_authenticated":False,
        "actual_kickoff_authenticated":False,
        "upstream_independence_authenticated":False,
        "independently_verified_regulation_ft":0,
        "certified_scored_cases":0,
        "model_accuracy_improved_proven":False,
        "positive_ev_verified":False,
        "production_recommendations":"DISABLED",
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory",type=Path,required=True)
    p.add_argument("--private-age-identity",type=Path,required=True)
    p.add_argument("--age-binary",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        print(json.dumps(replay(
            args.directory,identity_path=args.private_age_identity,
            age_binary=args.age_binary),sort_keys=True))
        return 0
    except (AuthorizedReplayError,SourceArchiveError,ValueError,
            OSError,TypeError,KeyError,OverflowError):
        print(json.dumps({
            "status":"HOLD","reason":"AUTHORIZED_SOURCE_REPLAY_REJECTED",
            "public_ciphertext_integrity_verified":False,
            "original_source_bytes_decrypted_and_replayed":False,
            "certified_scored_cases":0,
            "production_recommendations":"DISABLED",
        },sort_keys=True))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
