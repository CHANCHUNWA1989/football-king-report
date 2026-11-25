"""Fixed historical cohort replay. Never admit a result or certify publisher truth."""
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unicodedata
from datetime import datetime, timezone
from ops.openliga_capture_provenance import audit

ARCHIVE = "openliga_capture_provenance/2026/11/21/44886279496-1"
PINS = {"openliga-capture.tar.gz": ("89395e922aef770c4ee942d0dd31572074ccb6bb", 4_000_000),
        "capture.sigstore.json.gz": ("9767f20b97addcd129bb1ed2ae1c02b6e049666f", 2_000_000)}
ARCHIVE_HEAD = "e8054c34708295aae7227bc6c08429fdb8f02d30"
RUN_HEAD = "0e062a11d643320286e2ae142d56f86d19d803b5"
COHORT_BLOB = "12e72d988ae80081376f43aa510e910239c9d3f4"

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def norm(value):
    if not isinstance(value, str):
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", value).lower() if c.isascii() and c.isalnum())

def stamp(value):
    if not isinstance(value, str):
        raise ValueError("BAD_TIME")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(t.tzinfo is not None, "NAIVE_TIME")
    return t.astimezone(timezone.utc)

def compare(rows, expected):
    require(isinstance(rows, list), "NOT_LIST")
    indexed = {}
    for row in rows:
        require(isinstance(row, dict) and type(row.get("matchID")) is int, "BAD_ID")
        mid = row["matchID"]
        require(mid not in indexed, "DUPLICATE_PROVIDER_ID")
        indexed[mid] = row
    ids = set()
    observations = []
    for item in expected:
        mid = int(item["provider_fixture_id_hint"])
        require(mid not in ids, "DUPLICATE_COHORT_ID")
        ids.add(mid)
        league, home, away, scheduled = json.loads(item["archive_key"])
        row = indexed.get(mid)
        ok = False
        if row:
            ft = [q for q in row.get("matchResults", []) if isinstance(q, dict) and type(q.get("resultTypeID")) is int and q["resultTypeID"] == 2]
            score = [ft[0].get("pointsTeam1"), ft[0].get("pointsTeam2")] if len(ft) == 1 else []
            ok = (league == "bundesliga" and row.get("leagueShortcut") == "bl1"
                  and str(row.get("leagueSeason")) == "2026"
                  and row.get("matchIsFinished") is True
                  and norm(row.get("team1", {}).get("teamName")) == home
                  and norm(row.get("team2", {}).get("teamName")) == away
                  and stamp(row.get("matchDateTimeUTC")) == stamp(scheduled)
                  and len(score) == 2 and all(type(v) is int and 0 <= v <= 99 for v in score)
                  and score == item["published_score_ft"])
        observations.append({"provider_id": mid, "raw_record_present": row is not None,
                             "all_fields_match": bool(ok), "independently_verified": False})
    require(ids == set(range(83228, 83238)), "COHORT_ID_SET_MISMATCH")
    return observations

def main():
    archive_root = Path("archive-input")
    require(subprocess.check_output(["git", "-C", str(archive_root), "rev-parse", "HEAD"], text=True).strip() == ARCHIVE_HEAD, "ARCHIVE_HEAD_MISMATCH")
    cohort_raw = Path("research/intelligence_x/ft_observation_review_20261125.json").read_bytes()
    require(blob(cohort_raw) == COHORT_BLOB, "COHORT_BLOB_MISMATCH")
    expected = json.loads(cohort_raw)["cases"]
    with tempfile.TemporaryDirectory() as temp:
        proof = Path(temp)
        for name, (pin, maximum) in PINS.items():
            compressed = (archive_root / ARCHIVE / name).read_bytes()
            require(blob(compressed) == pin, "COMPRESSED_BLOB_MISMATCH")
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                raw = stream.read(maximum + 1)
            require(0 < len(raw) <= maximum, "DECOMPRESS_SIZE")
            (proof / name[:-3]).write_bytes(raw)
        report = audit(proof, source_sha=RUN_HEAD, workflow_sha=RUN_HEAD,
                       run_id="44886279496", attempt="1")
        require(report.get("audit_completed") is True
                and report.get("signature_identity_and_subject_verified") is True
                and report.get("capture_content_replayed") is True, "CAPTURE_AUDIT_FAILED:" + str(report.get("reason")))
        require(report.get("production_recommendations") == "DISABLED"
                and report.get("independently_verified") is False
                and report.get("eligible_for_model_scoring") is False, "UNSAFE_AUDIT")
        with tarfile.open(proof / "openliga-capture.tar", mode="r:") as tar:
            stream = tar.extractfile("openligadb.json")
            require(stream is not None, "RAW_MEMBER_MISSING")
            raw = stream.read(3_000_001)
        require(0 < len(raw) <= 3_000_000, "RAW_SIZE")
        require(hashlib.sha256(raw).hexdigest() == report["capture_summary"]["raw_sha256"], "RAW_DIGEST_MISMATCH")
        rows = json.loads(raw)
        observed = compare(rows, expected)
        # Negative controls: duplicate and one changed expected result.
        try:
            compare(rows + [rows[0]], expected)
        except ValueError as exc:
            require(str(exc) == "DUPLICATE_PROVIDER_ID", "WRONG_NEGATIVE_REASON")
        else:
            raise ValueError("DUPLICATE_NEGATIVE_FAILED")
        altered = copy.deepcopy(expected)
        matched = next((x for x in observed if x["all_fields_match"]), None)
        if matched:
            item = next(x for x in altered if int(x["provider_fixture_id_hint"]) == matched["provider_id"])
            item["published_score_ft"] = [98, 99]
            require(not next(x for x in compare(rows, altered) if x["provider_id"] == matched["provider_id"])["all_fields_match"], "SCORE_NEGATIVE_FAILED")
        print(json.dumps({"schema":"intelligence-x-raw-cohort-replay-v1",
              "capture_run":"44886279496", "signature_and_capture_replayed":True,
              "verified_tlog_utc": report["verified_tlog_utc"],
              "raw_sha256": hashlib.sha256(raw).hexdigest(),
              "cases": observed, "matched": sum(x["all_fields_match"] for x in observed),
              "duplicate_negative_passed": True, "score_negative_executed": matched is not None,
              "authenticated_settlements":0, "actual_kickoff_authenticated":False,
              "independent_source_origin_authenticated":False,
              "eligible_for_model_scoring":False, "status":"HOLD",
              "production_recommendations":"DISABLED"}, sort_keys=True))
        require(all(x["all_fields_match"] for x in observed), "COHORT_NOT_FULLY_MATCHED")

if __name__ == "__main__":
    main()
