"""Build a linked incremental custody subject; never replace the original proof."""
import argparse
import hashlib
import json
from pathlib import Path
from ops.archive_custody_subject import build, canonical, delta
from ops.archive_external_witness import EXPECTED_DIGEST, run
from ops.history_blob_retention_preflight import _unique, RetentionHold

OLD_SOURCE = "513f4e24f834091d3de038d55881d8ba9a744c79"
NEW_SOURCE = "6f40f84a1418ca4e2d42c8ba2bbd21a656d52a24"
OLD_CANDIDATE = "8fc67255419a81e4fad0ae5a3901be9ba99a345f"
NEW_CANDIDATE = "a7059fc5af1bf4465aced0fba914c526d121c5a4"
NEW_PATH = "sources/live_germany/history/2026/11/24/12-45395491049.json.gz"
POINTER = "sources/live_germany_latest.json"


def link(old, new):
    a, b = old["subject"], new["subject"]
    for report in (old, new):
        if hashlib.sha256(canonical(report["subject"])).hexdigest() != report["subject_sha256"]:
            raise RetentionHold("CUSTODY_SUBJECT_DIGEST_MISMATCH")
    if old["subject_sha256"] != EXPECTED_DIGEST:
        raise RetentionHold("PREVIOUS_SUBJECT_PIN_MISMATCH")
    if (a["source_main_sha"], b["source_main_sha"], a["archive_candidate_sha"],
        b["archive_candidate_sha"]) != (OLD_SOURCE, NEW_SOURCE, OLD_CANDIDATE, NEW_CANDIDATE):
        raise RetentionHold("CUSTODY_LINEAGE_PIN_MISMATCH")
    if a["archive_base_sha"] != b["archive_base_sha"]:
        raise RetentionHold("ARCHIVE_BASE_CHANGED")
    oldrows = {r["path"]:r for r in a["history_records"]}
    newrows = {r["path"]:r for r in b["history_records"]}
    if len(oldrows) != 88 or len(newrows) != 89 or set(newrows)-set(oldrows) != {NEW_PATH} or any(newrows.get(k)!=v for k,v in oldrows.items()):
        raise RetentionHold("HISTORY_LINEAGE_CHANGED")
    ap = {r["path"]:r for r in a["mutable_pointer_records"]}
    bp = {r["path"]:r for r in b["mutable_pointer_records"]}
    if len(ap)!=13 or set(ap)!=set(bp) or {k for k in ap if ap[k]!=bp[k]} != {POINTER}:
        raise RetentionHold("UNEXPECTED_MUTABLE_POINTER_DELTA")
    if any(ap[POINTER][k]!=bp[POINTER][k] for k in ("archive_blob_sha1","archive_sha256")):
        raise RetentionHold("ARCHIVE_POINTER_CHANGED")
    subject = dict(schema="football-king-linked-unsigned-custody-v1",
                   predecessor_subject_sha256=old["subject_sha256"],
                   current_subject_sha256=new["subject_sha256"],
                   current_subject=b, added_history_paths=[NEW_PATH],
                   changed_source_pointers=[POINTER], production_recommendations="DISABLED")
    return dict(status="HOLD_LINKED_UNSIGNED_CUSTODY_READY", subject=subject,
                linked_subject_sha256=hashlib.sha256(canonical(subject)).hexdigest(),
                predecessor_subject_sha256=old["subject_sha256"],
                current_subject_sha256=new["subject_sha256"], inherited_paths=88,
                new_paths=1, total_paths=89, external_signature_verified=False,
                trusted_timestamp_verified=False, independent_archive_retention_verified=False,
                hosted_archive_write_authorized=False, source_switch_authorized=False,
                production_recommendations="DISABLED")


def inspect(repo, previous, current):
    if delta(repo, OLD_SOURCE, NEW_SOURCE) != {NEW_PATH:"A", POINTER:"M"}:
        raise RetentionHold("UNEXPECTED_SOURCE_INCREMENT")
    if delta(repo, OLD_CANDIDATE, NEW_CANDIDATE) != {NEW_PATH:"A"}:
        raise RetentionHold("UNEXPECTED_CANDIDATE_INCREMENT")
    return link(build(repo, previous, OLD_CANDIDATE), build(repo, current, NEW_CANDIDATE))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True, type=Path)
    p.add_argument("--previous", required=True, type=Path)
    p.add_argument("--current", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    try:
        r = inspect(a.repo, json.loads(a.previous.read_bytes(),object_pairs_hook=_unique),
                    json.loads(a.current.read_bytes(),object_pairs_hook=_unique))
        a.out.mkdir(mode=0o700,exist_ok=False)
        subject=a.out/"linked-custody-subject.json"
        subject.write_bytes(canonical(r["subject"]))
        (a.out/"linked-custody.tsq").write_bytes(run(["openssl","ts","-query","-data",str(subject),"-sha256","-cert"]))
        print(json.dumps({k:v for k,v in r.items() if k!="subject"},sort_keys=True))
    except (ValueError,OSError,KeyError,TypeError,RuntimeError):
        print(json.dumps(dict(status="HOLD_INCREMENT_UNVERIFIABLE",production_recommendations="DISABLED")))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
