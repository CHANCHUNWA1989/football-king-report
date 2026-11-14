"""Private, create-only GitHub archive for pinned TheSportsDB raw observations.

Reuses the existing private-market destination authentication and scoped token
transport, but never uses market-pack schemas or publishes raw provider data.
A successful roundtrip proves private remote byte preservation at that commit;
it does NOT prove external publisher truth, independent upstream, actual KO, or
eligible settlement. The destination admin can still change/delete content.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re

from ops import private_response_archive as transport
from ops import private_response_capture as safeio
from ops.sportsdb_event_capture import FIXED_EVENTS, CaptureError, verify_capture

MAGIC = b"FOOTBALL-KING-SPORTSDB-RAW-RECEIPT-v1\n"
MAX_PACK_BYTES = 600_000
MANIFEST_LIMIT = 16_384


class EvidenceArchiveError(ValueError):
    """A fixed public status code; no secret, remote path or original body."""


def _require(condition, code):
    if not condition:
        raise EvidenceArchiveError(code)


def _safe_read(folder, event_id):
    proof = verify_capture(folder, event_id=event_id, require_live=True)
    descriptor = safeio._open_chain(safeio._path(folder))
    try:
        safeio._directory_mode(descriptor)
        _require(set(os.listdir(descriptor)) == {"sportsdb-event.json", "manifest.json"},
                 "PRIVATE_EVIDENCE_FILE_SET_CHANGED")
        raw = safeio._read(descriptor, "sportsdb-event.json", 512_000)
        manifest = safeio._read(descriptor, "manifest.json", MANIFEST_LIMIT)
    finally:
        os.close(descriptor)
    _require(hashlib.sha256(raw).hexdigest() == proof["raw_sha256"],
             "PRIVATE_EVIDENCE_CHANGED")
    _require(verify_capture(folder, event_id=event_id, require_live=True)
             == proof, "PRIVATE_EVIDENCE_CHANGED")
    return raw, manifest, proof


def _encode(raw, manifest):
    _require(0 < len(raw) <= 512_000 and 0 < len(manifest) <= MANIFEST_LIMIT,
             "PRIVATE_EVIDENCE_SIZE")
    packed = MAGIC + len(manifest).to_bytes(4, "big") + manifest + raw
    _require(len(packed) <= MAX_PACK_BYTES, "PRIVATE_EVIDENCE_SIZE")
    return packed


def _path(event_id, source_sha, run_id, attempt, raw_sha):
    _require(type(event_id) is str and event_id in FIXED_EVENTS,
             "PRIVATE_EVIDENCE_EVENT_ID")
    _require(type(source_sha) is str and re.fullmatch(r"[0-9a-f]{40}", source_sha),
             "PRIVATE_EVIDENCE_CONTEXT")
    _require(all(type(x) is str and re.fullmatch(r"[1-9][0-9]{0,19}", x)
                 for x in (run_id, attempt)), "PRIVATE_EVIDENCE_CONTEXT")
    _require(type(raw_sha) is str and re.fullmatch(r"[0-9a-f]{64}", raw_sha),
             "PRIVATE_EVIDENCE_CONTEXT")
    return ("result-evidence/thesportsdb/v1/" + event_id + "/" + source_sha
            + "/" + run_id + "-" + attempt + "/" + raw_sha + ".pack")


def _readback(client, path, blob, commit, checksum, expected):
    content = client.request("GET", client.base + "/contents/" + path + "?ref=" + commit,
                             accept="application/vnd.github.object+json")
    _require(type(content) is dict and content.get("type") == "file"
             and content.get("path") == path and content.get("sha") == blob
             and content.get("size") == len(expected), "PRIVATE_EVIDENCE_REACHABILITY")
    record = client.request("GET", client.base + "/git/blobs/" + blob,
                            maximum=2 * MAX_PACK_BYTES + 80_000)
    _require(type(record) is dict and record.get("sha") == blob
             and record.get("size") == len(expected)
             and record.get("encoding") == "base64"
             and type(record.get("content")) is str, "PRIVATE_EVIDENCE_BLOB")
    try:
        found = base64.b64decode(record["content"].replace("\n", ""),
                                 validate=True)
    except (ValueError, TypeError, base64.binascii.Error):
        raise EvidenceArchiveError("PRIVATE_EVIDENCE_BLOB") from None
    _require(found == expected
             and transport._blob_digest(found) == blob
             and hashlib.sha256(found).hexdigest() == checksum,
             "PRIVATE_EVIDENCE_READBACK_CHANGED")
    return found


def archive(folder, *, event_id, source_sha, run_id, attempt, config, opener=None):
    """Create one private repo object then pinned readback; no update/delete path."""
    try:
        _require(type(config) is transport.Configuration,
                 "PRIVATE_EVIDENCE_CONFIGURATION")
        raw, manifest, proof = _safe_read(folder, event_id)
        packed = _encode(raw, manifest)
        pin = proof["raw_sha256"]
        path = _path(event_id, source_sha, run_id, attempt, pin)
        blob = transport._blob_digest(packed)
        digest = hashlib.sha256(packed).hexdigest()
        client = transport._Client(config, opener)
        branch = client.target()
        client.initialized_branch(branch)
        _require(client.target() == branch, "PRIVATE_EVIDENCE_TARGET_CHANGED")
        receipt = client.request(
            "PUT", client.base + "/contents/" + path,
            data={"message": "Save privately verified source-observation bytes " + event_id,
                  "content": base64.b64encode(packed).decode("ascii"),
                  "branch": branch}, expected=201)
        _require(type(receipt) is dict and type(receipt.get("content")) is dict
                 and receipt["content"].get("sha") == blob
                 and type(receipt.get("commit")) is dict,
                 "PRIVATE_EVIDENCE_WRITE_RECEIPT")
        commit = transport._hash(receipt["commit"].get("sha"), 40)
        restored = _readback(client, path, blob, commit, digest, packed)
        _require(client.target() == branch and restored == packed,
                 "PRIVATE_EVIDENCE_TARGET_CHANGED")
        return {"status": "HOLD", "archive_status": "PRIVATE_REMOTE_READBACK_VERIFIED",
                "provider_event_id": event_id, "raw_sha256": pin,
                "raw_bytes": len(raw), "archive_sha256": digest,
                "archive_blob_sha": blob, "archive_commit_sha": commit,
                "source_commit_sha": source_sha, "run_id": run_id,
                "attempt": attempt, "private_storage_authenticated": True,
                "raw_integrity_replayed": True,
                "source_independence_authenticated": False,
                "actual_kickoff_authenticated": False,
                "independently_verified": False,
                "eligible_for_model_scoring": False,
                "production_recommendations": "DISABLED"}
    except (CaptureError, transport.ArchiveError, EvidenceArchiveError):
        raise
    except Exception:
        raise EvidenceArchiveError("PRIVATE_EVIDENCE_OPERATION_FAILED") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--event-id", choices=sorted(FIXED_EVENTS), required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    args = parser.parse_args(argv)
    try:
        result = archive(args.private_dir, event_id=args.event_id,
                         source_sha=args.source_sha, run_id=args.run_id,
                         attempt=args.attempt,
                         config=transport.configuration(required=True))
    except (CaptureError, transport.ArchiveError, EvidenceArchiveError) as exc:
        # Never include paths, private repo name or tokens in public logs.
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:80],
                          "private_storage_authenticated": False,
                          "independently_verified": False,
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
