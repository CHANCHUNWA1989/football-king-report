"""Read-only independently re-runnable PUBLIC ciphertext custody audit.

Validates the FIRST real 2026-11-08 dual-source response archive against
fixed original Git blob pin and exact per-file SHA256, including each ciphertext
chunk, joined ciphertext hashes and safe receipt semantics.

No private age identity: cipher/receipt consistency is NOT a decryption
roundtrip, independent publisher provenance or official 90-minute FT.
Git history is not third-party-notarized WORM storage.
"""
import argparse
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re

from ops.identity_ab_sealed_archive_audit import (
    _read, _parse, _git_blob, ForwardArchiveAuditError,
)
from ops.identity_ab_two_source_custody import (
    SCHEMA, TWO_SOURCES, YEAR, MAX_PART_BYTES, ENCRYPTION, COMPRESSION,
)
from ops.shadow_raw_source_collector import source_urls
from ops.identity_ab_forward_seal import _date as parse_time

RUN_DIRECTORY = "42446535384-1"
INDEX_GIT_BLOB_SHA1 = "8e7c2cfcda60033268cb492ab8e7be80691f28c1"
COMMIT = "fa7836e81ea59c9a11ff3d55afed7b2ba39a45e6"
OBSERVED = "2026-11-08T04:22:30.628969+00:00"
RECIPIENT_SHA256 = "a8dc3f96b0063a6fa5293e2a9e709ad5e012a6f24a54ca85fea88333d73b62ac"
INDEX_KEYS = frozenset((
    "schema","status","github_run_id","github_run_attempt",
    "source_commit","result_observed_utc","source_count","sources",
    "file_sha256","index_is_not_worm_or_third_party_notarized",
    "source_upstream_independence_authenticated",
    "independently_verified_regulation_ft","certified_case_count",
    "production_recommendations",
))
RECEIPT_KEYS = frozenset((
    "schema","status","provider","source_url","source_received_utc",
    "source_raw_sha256","source_raw_bytes",
    "compressed_original_pack_sha256","compressed_original_pack_bytes",
    "encrypted_ciphertext_sha256","encrypted_ciphertext_bytes",
    "chunk_sha256","recipient_sha256","compression","encryption",
    "source_commit","github_run_id","github_run_attempt",
    "source_publisher_authenticated","upstream_independence_authenticated",
    "regulation_ft_authenticated","actual_kickoff_authenticated",
    "eligible_for_model_scoring","certified_case_count",
    "production_recommendations",
))


class SourceArchiveError(ValueError):
    """Never disclose provider raw JSON or key materials."""


def _require(ok, code):
    if not ok:
        raise SourceArchiveError(code)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(directory):
    root=Path(directory)
    _require(root.is_dir() and not root.is_symlink()
             and root.name==RUN_DIRECTORY
             and not any(x.is_symlink() for x in root.parents),
             "INVALID_SOURCE_CUSTODY_FOLDER")
    raw_index=_read(root,"index.json",16_384)
    _require(_git_blob(raw_index)==INDEX_GIT_BLOB_SHA1,
             "ORIGINAL_SOURCE_CUSTODY_INDEX_CHANGED")
    index=_parse(raw_index,expected=INDEX_KEYS)
    _require(index["schema"]==SCHEMA and index["status"]=="HOLD"
             and index["source_commit"]==COMMIT
             and index["result_observed_utc"]==OBSERVED
             and index["github_run_id"]==RUN_DIRECTORY.split("-")[0]
             and index["github_run_attempt"]==RUN_DIRECTORY.split("-")[1]
             and type(index["source_count"]) is int and index["source_count"]==2
             and index["index_is_not_worm_or_third_party_notarized"] is True
             and index["source_upstream_independence_authenticated"] is False
             and type(index["independently_verified_regulation_ft"]) is int
             and index["independently_verified_regulation_ft"]==0
             and type(index["certified_case_count"]) is int
             and index["certified_case_count"]==0
             and index["production_recommendations"]=="DISABLED"
             and type(index["sources"]) is dict
             and set(index["sources"])==set(TWO_SOURCES)
             and type(index["file_sha256"]) is dict,
             "UNTRUSTED_SOURCE_CUSTODY_INDEX")
    expected_files=set(index["file_sha256"])|{"index.json"}
    _require({p.name for p in root.iterdir()}==expected_files,
             "SOURCE_CUSTODY_EXTRA_OR_MISSING_FILE")
    _require(len(expected_files)<=190,
             "TOO_MANY_CUSTODY_FILES")
    for name, expected in index["file_sha256"].items():
        _require(type(name) is str
                 and re.fullmatch(
                     r"(OpenLigaDB|OpenFootball)(\.age\.part[0-9]{3}|\.receipt\.json)",
                     name) is not None
                 and type(expected) is str
                 and re.fullmatch(r"[0-9a-f]{64}",expected) is not None,
                 "INVALID_SOURCE_CUSTODY_FILE_ENTRY")
    observation=parse_time(OBSERVED)
    source_shas={}
    chunks_total=0
    receipt_count=0
    for provider in TWO_SOURCES:
        meta=index["sources"][provider]
        _require(type(meta) is dict
                 and set(meta)=={
                    "receipt_file","receipt_sha256","ciphertext_sha256",
                    "parts","source_raw_sha256",
                 } and type(meta["parts"]) is list
                 and 0<len(meta["parts"])<=90,
                 "INVALID_CUSTODY_PROVIDER_INDEX")
        receipt_name=provider+".receipt.json"
        _require(meta["receipt_file"]==receipt_name
                 and index["file_sha256"].get(receipt_name)==meta["receipt_sha256"],
                 "SOURCE_RECEIPT_INDEX_MISMATCH")
        raw_receipt=_read(root,receipt_name,8192)
        _require(_digest(raw_receipt)==meta["receipt_sha256"],
                 "SOURCE_RECEIPT_BYTES_CHANGED")
        receipt=_parse(raw_receipt,expected=RECEIPT_KEYS)
        chunks=meta["parts"]
        _require(chunks==[f"{provider}.age.part{i:03d}"
                           for i in range(len(chunks))]
                 and type(receipt["chunk_sha256"]) is dict
                 and list(receipt["chunk_sha256"])==chunks,
                 "UNSAFE_CIPHERTEXT_CHUNK_ORDER")
        full=b""
        for name in chunks:
            _require(name in index["file_sha256"]
                     and receipt["chunk_sha256"].get(name)==index["file_sha256"][name],
                     "SOURCE_CIPHER_CHUNK_PIN_MISMATCH")
            chunk=_read(root,name,MAX_PART_BYTES)
            _require(_digest(chunk)==index["file_sha256"][name],
                     "SOURCE_CIPHER_BYTES_CHANGED")
            full+=chunk
        captured=parse_time(receipt["source_received_utc"])
        _require(receipt["schema"]==SCHEMA
                 and receipt["status"]=="HOLD"
                 and receipt["provider"]==provider
                 and receipt["source_url"]==source_urls(YEAR)[provider]
                 and receipt["source_commit"]==COMMIT
                 and receipt["github_run_id"]==index["github_run_id"]
                 and receipt["github_run_attempt"]==index["github_run_attempt"]
                 and receipt["recipient_sha256"]==RECIPIENT_SHA256
                 and receipt["encryption"]==ENCRYPTION
                 and receipt["compression"]==COMPRESSION
                 and type(receipt["source_raw_bytes"]) is int
                 and 0<receipt["source_raw_bytes"]<=3_000_000
                 and type(receipt["compressed_original_pack_bytes"]) is int
                 and 0<receipt["compressed_original_pack_bytes"]<=3_100_000
                 and type(receipt["encrypted_ciphertext_bytes"]) is int
                 and receipt["encrypted_ciphertext_bytes"]==len(full)
                 and _digest(full)==receipt["encrypted_ciphertext_sha256"]
                 ==meta["ciphertext_sha256"]
                 and receipt["source_raw_sha256"]==meta["source_raw_sha256"]
                 and receipt["source_publisher_authenticated"] is False
                 and receipt["upstream_independence_authenticated"] is False
                 and receipt["regulation_ft_authenticated"] is False
                 and receipt["actual_kickoff_authenticated"] is False
                 and receipt["eligible_for_model_scoring"] is False
                 and type(receipt["certified_case_count"]) is int
                 and receipt["certified_case_count"]==0
                 and receipt["production_recommendations"]=="DISABLED"
                 and captured<=observation
                 and observation-captured<=timedelta(minutes=10),
                 "CIPHER_RECEIPT_SEMANTICS_INVALID")
        source_shas[provider]=receipt["source_raw_sha256"]
        chunks_total+=len(chunks)
        receipt_count+=1
    _require(len(index["file_sha256"])==chunks_total+receipt_count,
             "CUSTODY_INDEX_UNEXPECTED_UNACCOUNTED_FILES")
    return {
        "schema":"football-king-two-source-public-cipher-replay-v1",
        "status":"HOLD",
        "original_custody_index_git_blob_sha1":INDEX_GIT_BLOB_SHA1,
        "original_source_counts":2,
        "sealed_ciphertext_chunks":chunks_total,
        "sealed_receipts":receipt_count,
        "verified_public_files":chunks_total+receipt_count+1,
        "public_source_ciphertext_integrity_verified":True,
        "original_source_raw_sha256":source_shas,
        "private_decryption_verified":False,
        "publisher_truth_authenticated":False,
        "upstream_independence_authenticated":False,
        "independently_verified_regulation_ft":0,
        "certified_scored_case_count":0,
        "production_recommendations":"DISABLED",
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.directory),sort_keys=True))
        return 0
    except (SourceArchiveError,ForwardArchiveAuditError,
            OSError,ValueError,TypeError,KeyError,OverflowError):
        print(json.dumps({
            "status":"HOLD","reason":"SOURCE_CIPHERTEXT_REPLAY_REJECTED",
            "public_source_ciphertext_integrity_verified":False,
            "private_decryption_verified":False,
            "certified_scored_case_count":0,
            "production_recommendations":"DISABLED",
        },sort_keys=True))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
