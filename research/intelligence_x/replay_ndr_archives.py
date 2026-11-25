"""Reverify two fixed NDR archives and inventory their native IDs. Research only."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from ops.ndr_capture_provenance import audit
from ops.ndr_capture_pack import _members
from ops.ndr_result_observations import observe

ARCHIVE_HEAD = "e8054c34708295aae7227bc6c08429fdb8f02d30"
PACKS = [
    ("09", "42551444357", "293efc8b8a05ac2ea88972c736870755d612f26d",
     "1549639e0867c2328903d57d3709352c605355ae", "408071ffd27d06d47d9ccc879406ba38d48b3aab"),
    ("21", "44886279496", "0e062a11d643320286e2ae142d56f86d19d803b5",
     "e9ff5429b4536b317e13d0d576b5f8504c4a1c9b", "346bb586cf5ffb3c97985750aedc1122f3abcd67"),
]

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def unpack(path, pin, max_size):
    require(path.is_file() and 0 < path.stat().st_size <= 2_000_000, "COMPRESSED_SIZE")
    raw = path.read_bytes()
    require(git_blob(raw) == pin, "COMPRESSED_BLOB_MISMATCH")
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        output = stream.read(max_size + 1)
    require(0 < len(output) <= max_size, "UNCOMPRESSED_SIZE")
    return output

def inventory(rows):
    require(isinstance(rows, list), "INVALID_ROWS")
    by_id = {}
    for row in rows:
        require(isinstance(row, dict) and row.get("provider") == "NDR"
                and row.get("independently_verified") is False
                and row.get("eligible_for_model_scoring") is False, "UNSAFE_ROW")
        mid = row.get("provider_fixture_id")
        require(isinstance(mid, str) and mid.isascii() and mid.isdigit() and not mid.startswith("0")
                and len(mid) <= 10 and mid not in by_id, "INVALID_OR_DUPLICATE_NATIVE_ID")
        by_id[mid] = row
    return by_id

def main():
    archive = Path("archive-input")
    require(subprocess.check_output(["git", "-C", str(archive), "rev-parse", "HEAD"], text=True).strip() == ARCHIVE_HEAD,
            "ARCHIVE_HEAD_MISMATCH")
    observed = []
    all_index = set()
    all_details = set()
    for day, run, head, tar_pin, bundle_pin in PACKS:
        root = archive / "ndr_capture_provenance" / "2026" / "11" / day / (run + "-1")
        with tempfile.TemporaryDirectory() as temporary:
            proof = Path(temporary)
            tar = unpack(root / "ndr-capture.tar.gz", tar_pin, 16_000_000)
            bundle = unpack(root / "capture.sigstore.json.gz", bundle_pin, 2_000_000)
            (proof / "ndr-capture.tar").write_bytes(tar)
            (proof / "capture.sigstore.json").write_bytes(bundle)
            checked = audit(proof, source_sha=head, workflow_sha=head, run_id=run, attempt="1")
            require(checked.get("audit_completed") is True
                    and checked.get("signature_identity_and_subject_verified") is True
                    and checked.get("capture_content_replayed") is True, "NDR_REPLAY_FAILED:" + str(checked.get("reason")))
            require(checked.get("production_recommendations") == "DISABLED"
                    and checked.get("independently_verified") is False
                    and checked.get("eligible_for_model_scoring") is False, "UNSAFE_REPORT")
            files = _members(tar)
            folder = proof / "index"
            folder.mkdir()
            (folder / "manifest.json").write_bytes(files["index-manifest.json"])
            if "ndr.html" in files:
                (folder / "ndr.html").write_bytes(files["ndr.html"])
            index = observe(folder)
            ix = inventory(index["observations"])
            details = inventory(json.loads(files["report.json"])["observations"])
            require(set(details) <= set(ix), "DETAIL_NOT_IN_INDEX")
            for mid, row in details.items():
                require(row.get("display_score") == ix[mid].get("display_score"), "DETAIL_SCORE_CONFLICT")
            require(len(ix) == checked["capture_summary"]["index_observation_count"]
                    and len(details) == checked["capture_summary"]["observation_count"], "REPLAY_COUNT_MISMATCH")
            all_index.update(ix)
            all_details.update(details)
            observed.append({"run":run, "verified_tlog_utc":checked["verified_tlog_utc"],
                             "index_native_ids":sorted(ix,key=int), "detail_native_ids":sorted(details,key=int),
                             "index_count":len(ix), "detail_count":len(details),
                             "subject_sha256":checked["subject_sha256"]["ndr-capture.tar"]})
            if ix:
                try:
                    inventory(list(ix.values())+[next(iter(ix.values()))])
                except ValueError as exc:
                    require(str(exc) == "INVALID_OR_DUPLICATE_NATIVE_ID", "WRONG_NEGATIVE_REASON")
                else:
                    raise ValueError("DUPLICATE_NEGATIVE_FAILED")
    require(len(observed)==2, "INCOMPLETE_PACKS")
    print(json.dumps({"schema":"intelligence-x-ndr-archive-replay-v1", "packs":observed,
                      "packs_reverified":len(observed), "unique_index_ids":len(all_index),
                      "unique_detail_ids":len(all_details), "cross_provider_fixture_mapping_verified":False,
                      "independent_upstream_authenticated":False, "actual_kickoff_authenticated":False,
                      "authenticated_settlements":0, "eligible_for_model_scoring":False,
                      "status":"HOLD", "production_recommendations":"DISABLED"},sort_keys=True))
if __name__ == "__main__":
    main()
