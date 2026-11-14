"""Encrypt ORIGINAL paired result-source HTTP bytes before public evidence upload.

The same two bounded responses used by the 19-fixture candidate linker are
compressed and age-v1.3.2-native-pq encrypted under the previously registered
PUBLIC recipient. Only ciphertext chunks + safe receipts + index are saved.
There is no local secret key, no claimed publisher origin, no independent FT,
and no WORM or third-party timestamp guarantee.

Authorized keyholders can later verify pack SHA/raw SHA after decryption.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import zlib

from ops import private_response_relay as relay
from ops.shadow_raw_source_collector import (
    MAX_BYTES, source_urls, validate_json_body, allowed_media_types,
)
from ops.identity_ab_two_provider_result_review import TWO_SOURCES, YEAR
from ops.identity_ab_forward_seal import _date as parse_time

SCHEMA = "football-king-pq-two-provider-source-custody-v1"
MAGIC = b"FOOTBALL-KING-RESULT-RAW-ZLIB-AGE-v1\n"
MAX_PART_BYTES = 48_000
MAX_PARTS_PER_SOURCE = 90
MAX_CIPHER_BYTES = MAX_BYTES + 150_000
MAX_PACK_BYTES = MAX_BYTES + 65_536
MAX_ENVELOPE_HEADER = 4_096
COMPRESSION = "zlib-deflate-level-9"
ENCRYPTION = "age-v1.3.2-native-pq"
RECEIPT_SUFFIX = ".receipt.json"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
RUN = re.compile(r"[1-9][0-9]{0,19}\Z")
ATTEMPT = re.compile(r"[1-9][0-9]{0,5}\Z")


class CustodyError(ValueError):
    """Constant non-provider exception only."""


def _require(ok, code):
    if not ok:
        raise CustodyError(code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False)+"\n").encode()


def _pack(raw, meta, provider):
    """Self-describing compressed original; never published unencrypted."""
    url = source_urls(YEAR)[provider]
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES,
             "UNSAFE_OR_OVERSIZED_SOURCE")
    validate_json_body(raw, provider)
    _require(type(meta) is dict
             and meta.get("url") == url
             and meta.get("final_url") == url
             and meta.get("status") == 200
             and meta.get("media") in allowed_media_types(provider),
             "UNTRUSTED_HTTP_SOURCE_RECEIPT")
    captured = parse_time(meta.get("received_utc"))
    manifest = {
        "schema":SCHEMA,"provider":provider,"request_url":url,
        "final_url":url,"http_status":200,"content_type":meta["media"],
        "received_utc":captured.isoformat(),"raw_sha256":_sha(raw),
        "raw_bytes":len(raw),"compression":COMPRESSION,
        "source_publisher_authenticated":False,
        "upstream_independence_authenticated":False,
        "actual_kickoff_authenticated":False,
        "regulation_ft_authenticated":False,
        "production_recommendations":"DISABLED",
    }
    head = _json_bytes(manifest)
    _require(len(head) <= MAX_ENVELOPE_HEADER,"SOURCE_HEADER_TOO_LARGE")
    packed = MAGIC + len(head).to_bytes(4,"big") + head + zlib.compress(raw,9)
    _require(len(packed) <= MAX_PACK_BYTES,"SOURCE_PACK_TOO_LARGE")
    return packed, manifest


def _write_once(folder, entries):
    _require(folder.is_absolute() and not folder.exists()
             and folder.parent.is_dir() and not folder.parent.is_symlink()
             and not any(part.is_symlink() for part in folder.parents),
             "UNSAFE_SOURCE_CUSTODY_DESTINATION")
    folder.mkdir(mode=0o700)
    try:
        for name, body in sorted(entries.items()):
            _require(type(name) is str and "/" not in name and "\\" not in name
                     and not name.startswith("."), "INVALID_SOURCE_CUSTODY_FILENAME")
            fd = os.open(folder/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL
                         |getattr(os,"O_NOFOLLOW",0),0o600)
            with os.fdopen(fd,"wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            info=(folder/name).lstat()
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink==1
                     and info.st_mode&0o077==0
                     and (folder/name).read_bytes()==body,
                     "SOURCE_CUSTODY_LOCAL_READBACK_FAILED")
    except BaseException:
        for name in entries:
            try:(folder/name).unlink(missing_ok=True)
            except OSError:pass
        try:folder.rmdir()
        except OSError:pass
        raise


def capture(directory, sources, receipts, *, report, source_commit,
            run_id, attempt, age_binary, recipient_path):
    """Two-source all-or-none local preparation before create-only GH upload."""
    _require(type(sources) is dict and set(sources)==set(TWO_SOURCES)
             and type(receipts) is dict and set(receipts)==set(TWO_SOURCES),
             "INCOMPLETE_TWO_SOURCE_CUSTODY")
    _require(type(report) is dict and report.get("status")=="HOLD"
             and report.get("original_forecast_count")==19
             and report.get("certified_scored_cases")==0
             and report.get("upstream_independence_authenticated") is False
             and report.get("production_recommendations")=="DISABLED",
             "UNTRUSTED_TWO_SOURCE_REVIEW")
    _require(type(source_commit) is str and HEX40.fullmatch(source_commit)
             and type(run_id) is str and RUN.fullmatch(run_id)
             and type(attempt) is str and ATTEMPT.fullmatch(attempt),
             "UNSAFE_CUSTODY_RUN_IDENTITY")
    observation=parse_time(report.get("observed_utc"))
    recipient_raw=relay._read(Path(recipient_path),4096,private=False)
    try:
        recipient=relay._recipient(recipient_raw.decode("ascii").strip())
    except (UnicodeError,ValueError):
        raise CustodyError("INVALID_PUBLIC_AGE_RECIPIENT") from None
    _require(recipient_raw.strip()==recipient.encode("ascii"),
             "INVALID_PUBLIC_AGE_RECIPIENT")
    files={}
    sources_index={}
    for provider in TWO_SOURCES:
        raw=sources[provider]
        packed, header = _pack(raw,receipts[provider],provider)
        instant=parse_time(header["received_utc"])
        _require(instant<=observation
                 and (observation-instant).total_seconds()<=600,
                 "SOURCE_OBSERVATION_TIMESTAMP_CONFLICT")
        _require(report.get("source_hashes_sha256",{}).get(provider)==_sha(raw),
                 "SOURCE_CHANGED_AFTER_RESULT_COMPARISON")
        try:
            ciphertext=relay._crypto(packed,["--encrypt","-r",recipient],
                                     Path(age_binary),maximum=MAX_CIPHER_BYTES)
        except (relay.RelayError, OSError, ValueError):
            raise CustodyError("PINNED_PQ_ENCRYPTION_FAILED") from None
        _require(type(ciphertext) is bytes and len(ciphertext)>64
                 and len(ciphertext)<=MAX_CIPHER_BYTES,
                 "INVALID_SOURCE_CIPHERTEXT")
        chunks=[ciphertext[i:i+MAX_PART_BYTES]
                for i in range(0,len(ciphertext),MAX_PART_BYTES)]
        _require(0<len(chunks)<=MAX_PARTS_PER_SOURCE,
                 "SOURCE_CIPHERTEXT_TOO_MANY_PARTS")
        part_hashes={}
        for idx,chunk in enumerate(chunks):
            name=f"{provider}.age.part{idx:03d}"
            files[name]=chunk
            part_hashes[name]=_sha(chunk)
        receipt={
            "schema":SCHEMA,"status":"HOLD",
            "provider":provider,"source_url":header["request_url"],
            "source_received_utc":header["received_utc"],
            "source_raw_sha256":header["raw_sha256"],
            "source_raw_bytes":header["raw_bytes"],
            "compressed_original_pack_sha256":_sha(packed),
            "compressed_original_pack_bytes":len(packed),
            "encrypted_ciphertext_sha256":_sha(ciphertext),
            "encrypted_ciphertext_bytes":len(ciphertext),
            "chunk_sha256":part_hashes,
            "recipient_sha256":_sha(recipient.encode()),
            "compression":COMPRESSION,"encryption":ENCRYPTION,
            "source_commit":source_commit,
            "github_run_id":run_id,"github_run_attempt":attempt,
            "source_publisher_authenticated":False,
            "upstream_independence_authenticated":False,
            "regulation_ft_authenticated":False,
            "actual_kickoff_authenticated":False,
            "eligible_for_model_scoring":False,
            "certified_case_count":0,
            "production_recommendations":"DISABLED",
        }
        receipt_name=provider+RECEIPT_SUFFIX
        files[receipt_name]=_json_bytes(receipt)
        sources_index[provider]={
            "receipt_file":receipt_name,
            "receipt_sha256":_sha(files[receipt_name]),
            "ciphertext_sha256":_sha(ciphertext),
            "parts":list(part_hashes),
            "source_raw_sha256":header["raw_sha256"],
        }
    index={
        "schema":SCHEMA,"status":"HOLD",
        "github_run_id":run_id,"github_run_attempt":attempt,
        "source_commit":source_commit,
        "result_observed_utc":observation.isoformat(),
        "source_count":len(TWO_SOURCES),
        "sources":sources_index,
        "file_sha256":{k:_sha(v) for k,v in sorted(files.items())},
        "index_is_not_worm_or_third_party_notarized":True,
        "source_upstream_independence_authenticated":False,
        "independently_verified_regulation_ft":0,
        "certified_case_count":0,
        "production_recommendations":"DISABLED",
    }
    files["index.json"]=_json_bytes(index)
    _write_once(Path(directory),files)
    return {
        "status":"HOLD","source_count":2,"local_file_count":len(files),
        "ciphertext_parts":sum(len(v["parts"]) for v in sources_index.values()),
        "index_sha256":_sha(files["index.json"]),
        "source_originals_encrypted":True,
        "source_ciphertexts_remotely_preserved":False,
        "upstream_independence_authenticated":False,
        "certified_case_count":0,
        "production_recommendations":"DISABLED",
    }
