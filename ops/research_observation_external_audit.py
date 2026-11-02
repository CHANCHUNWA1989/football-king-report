"""Offline cross-check of a GitHub research artifact against GH API metadata.

Caller MUST retrieve metadata from GitHub independently (e.g. GitHub REST).
This tool does not query GitHub or authenticate JSON metadata cryptographically.
Validates archive bytes, API-reported archive SHA256, run/attempt/repo/commit,
upload and capture time ordering, then replays original research decisions.
No chat timestamp, executable price or independently certified outcome.
"""
import argparse
import hashlib
import io
import json
import re
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile, BadZipFile, LargeZipFile

from research_observation_reverify import verify, MAX_MANIFEST_BYTES, SOURCE_FILE, MANIFEST_FILE
from research_run_observation import MAX_INPUT_BYTES, _utc

REPOSITORY = "CHANCHUNWA1989/football-king-report"
WORKFLOW = ".github/workflows/football-king-iphone.yml"
ARTIFACT_NAME = "football-king-research-decision-observation"
MAX_ARCHIVE_BYTES = 4_000_000
MAX_METADATA_BYTES = 100_000


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _stamp(doc, key):
    return _utc(doc.get(key))


def _read_zip(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_ARCHIVE_BYTES,
             "INVALID_ZIP_SIZE")
    try:
        with ZipFile(io.BytesIO(raw)) as z:
            members = z.infolist()
            _require(len(members) == 2 and {m.filename for m in members} ==
                     {SOURCE_FILE, MANIFEST_FILE}, "UNSAFE_ZIP_INVENTORY")
            stored = {}
            for member in members:
                _require(not member.is_dir(), "UNSAFE_ZIP_FILE_TYPE")
                mode = member.external_attr >> 16
                _require(not mode or stat.S_IFMT(mode) in (0, stat.S_IFREG),
                         "UNSAFE_ZIP_FILE_TYPE")
                limit = (MAX_INPUT_BYTES if member.filename == SOURCE_FILE
                         else MAX_MANIFEST_BYTES)
                _require(0 < member.file_size <= limit, "UNSAFE_ZIP_FILE_SIZE")
                with z.open(member) as stream:
                    data = stream.read(limit + 1)
                _require(len(data) == member.file_size and len(data) <= limit,
                         "UNSAFE_ZIP_FILE_SIZE")
                stored[member.filename] = data
            _require(z.testzip() is None, "ZIP_CRC_MISMATCH")
        return stored
    except (BadZipFile, LargeZipFile, OSError, RuntimeError, EOFError):
        raise ValueError("INVALID_ZIP_FILE") from None


def audit(zip_bytes, run, artifact, *, now=None):
    _require(isinstance(run, dict) and isinstance(artifact, dict),
             "MISSING_GITHUB_METADATA")
    now = datetime.now(timezone.utc) if now is None else now
    _require(isinstance(now, datetime) and now.tzinfo is not None,
             "INVALID_VALIDATION_CLOCK")
    now = now.astimezone(timezone.utc)
    repo = run.get("repository")
    head_repo = run.get("head_repository")
    _require(type(run.get("id")) is int and run["id"] > 0
             and type(run.get("run_attempt")) is int and run["run_attempt"] > 0
             and isinstance(repo, dict) and isinstance(head_repo, dict)
             and type(repo.get("id")) is int and repo["id"] > 0
             and repo.get("full_name") == REPOSITORY
             and head_repo.get("id") == repo["id"]
             and head_repo.get("full_name") == REPOSITORY
             and run.get("path") == WORKFLOW
             and run.get("head_branch") == "main"
             and type(run.get("head_sha")) is str
             and re.fullmatch(r"[0-9a-f]{40}", run["head_sha"])
             and run.get("status") == "completed"
             and run.get("conclusion") == "success",
             "INVALID_GITHUB_RUN_METADATA")
    run_start = _stamp(run, "run_started_at")
    run_created = _stamp(run, "created_at")
    run_end = _stamp(run, "updated_at")
    _require(run_created <= run_start <= run_end <= now + timedelta(minutes=1),
             "GITHUB_RUN_TIME_CONFLICT")

    link = artifact.get("workflow_run")
    _require(type(artifact.get("id")) is int and artifact["id"] > 0
             and artifact.get("name") == ARTIFACT_NAME
             and artifact.get("expired") is False
             and isinstance(link, dict)
             and type(link.get("id")) is int and link["id"] == run["id"]
             and type(link.get("repository_id")) is int
             and link["repository_id"] == repo["id"]
             and type(link.get("head_repository_id")) is int
             and link["head_repository_id"] == repo["id"]
             and link.get("head_branch") == "main"
             and link.get("head_sha") == run["head_sha"],
             "GITHUB_ARTIFACT_RUN_MISMATCH")
    if "expires_at" in artifact:
        _require(_stamp(artifact, "expires_at") > now,
                 "GITHUB_ARTIFACT_EXPIRED")
    artifact_created = _stamp(artifact, "created_at")
    artifact_updated = _stamp(artifact, "updated_at")
    _require(run_start - timedelta(seconds=30) <= artifact_created
             <= artifact_updated <= run_end + timedelta(minutes=1),
             "GITHUB_ARTIFACT_TIME_CONFLICT")
    digest = artifact.get("digest")
    _require(type(digest) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", digest),
             "MISSING_OR_INVALID_ARTIFACT_DIGEST")
    _require(hashlib.sha256(zip_bytes).hexdigest() == digest[7:],
             "ZIP_DIGEST_MISMATCH")

    stored = _read_zip(zip_bytes)
    with tempfile.TemporaryDirectory(prefix="gh-artifact-audit-") as temp:
        folder = Path(temp)
        for filename, raw in stored.items():
            (folder / filename).write_bytes(raw)
        observed = verify(folder, run_id=str(run["id"]),
                          attempt=str(run["run_attempt"]), sha=run["head_sha"])
    clock = _utc(observed["observed_utc_runner_clock"])
    _require(run_start - timedelta(seconds=30) <= clock
             <= artifact_created + timedelta(seconds=30)
             and 0 <= (artifact_created - clock).total_seconds() <= 1800,
             "RESEARCH_OBSERVATION_OUTSIDE_GITHUB_RUN")
    return {
        "schema": "football-king-external-research-artifact-audit-v1",
        "status": observed["status"],
        "run_id": str(run["id"]),
        "run_attempt": str(run["run_attempt"]),
        "workflow_source_commit_sha": run["head_sha"],
        "artifact_id": artifact["id"],
        "observed_count": observed["observed_count"],
        "research_selections_sha256": observed["research_selections_sha256"],
        "github_reported_artifact_sha256": digest[7:],
        "artifact_zip_digest_verified_against_metadata": True,
        "run_identity_consistent_with_metadata": True,
        "metadata_time_window_consistent": True,
        "github_metadata_cryptographically_authenticated_by_tool": False,
        "chat_message_time_authenticated": False,
        "independent_match_outcome_authenticated": False,
        "can_enter_formal_settlement_ledger": False,
        "certified_forward_samples": 0,
        "roi": None, "ev": None,
        "production_recommendations": "DISABLED",
        "notice_zh": (
            "已重算原始研究檔及壓縮檔雜湊，並交叉核對外部提供嘅"
            "GitHub執行／Artifact欄位及時間；工具並未自行獨立獲取或"
            "簽章認證GitHub元數據，亦不證明ChatGPT對話時刻、比賽結果或正EV。"
        ),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zip", required=True)
    p.add_argument("--run-metadata", required=True)
    p.add_argument("--artifact-metadata", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    archive = Path(args.zip)
    _require(archive.is_file() and not archive.is_symlink()
             and 0 < archive.stat().st_size <= MAX_ARCHIVE_BYTES, "UNSAFE_ZIP_INPUT")
    def load(path):
        filename = Path(path)
        _require(filename.is_file() and not filename.is_symlink()
                 and 0 < filename.stat().st_size <= MAX_METADATA_BYTES,
                 "UNSAFE_METADATA_INPUT")
        return json.loads(filename.read_bytes())
    report = audit(archive.read_bytes(), load(args.run_metadata),
                   load(args.artifact_metadata))
    destination = Path(args.output)
    _require(not destination.is_symlink() and destination.resolve() != archive.resolve(),
             "UNSAFE_AUDIT_OUTPUT")
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                      allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"],
                      "artifact_zip_digest_verified_against_metadata": True,
                      "certified_forward_samples": 0,
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
