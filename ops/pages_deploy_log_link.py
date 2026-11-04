"""S0: verify actual GitHub Pages deployment log links run, artifact ID and head.

Completely offline checks for captured GitHub JSON + redacted Actions publish
job log. This is corroboration WITHIN GitHub, not independent identity
attestation, proof of source freshness, or authorization to release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from pages_artifact_readback import valid_run, strict_json

MAX_META = 750_000
MAX_LOG = 2_000_000
LOG_PREFIX = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z ")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _file(path, max_bytes: int) -> bytes:
    p = Path(path)
    if p.is_symlink() or not p.is_file() or not (0 < p.stat().st_size <= max_bytes):
        raise ValueError("S0_DEPLOY_EVIDENCE_UNSAFE_FILE")
    return p.read_bytes()


def _lines(raw_log: bytes) -> list[str]:
    if len(raw_log) > MAX_LOG:
        raise ValueError("S0_DEPLOY_LOG_OVERSIZE")
    lines = []
    for line in raw_log.decode("utf-8", errors="strict").splitlines():
        if not LOG_PREFIX.match(line):
            continue
        message = LOG_PREFIX.sub("", line, count=1)
        # GitHub host Actions may show progress/ANSI decorations. Do not
        # trust arbitrary text embedded in commands or user data.
        message = re.sub(r"\x1b\[[0-9;]*m", "", message)
        lines.append(message)
    return lines


def validate(run: dict, jobs: dict, artifacts: dict, log: bytes) -> dict:
    run_id, sha, _, _ = valid_run(run)
    if (not isinstance(jobs, dict) or not isinstance(jobs.get("jobs"), list)
            or jobs.get("total_count") != len(jobs["jobs"])
            or len(jobs["jobs"]) > 100):
        raise ValueError("S0_DEPLOY_JOBS_RESPONSE_INCOMPLETE")
    publishers = [j for j in jobs["jobs"] if isinstance(j, dict) and j.get("name") == "publish"]
    if (len(publishers) != 1 or type(publishers[0].get("id")) is not int
            or publishers[0].get("run_id") != run_id
            or publishers[0].get("status") != "completed"
            or publishers[0].get("conclusion") != "success"):
        raise ValueError("S0_DEPLOY_PUBLISH_JOB_UNVERIFIED")
    steps = publishers[0].get("steps")
    if (not isinstance(steps, list)
            or len([s for s in steps if isinstance(s, dict) and
                    s.get("name") == "Deploy mobile site" and
                    s.get("conclusion") == "success"]) != 1):
        raise ValueError("S0_DEPLOY_STEP_UNVERIFIED")
    if (not isinstance(artifacts, dict)
            or not isinstance(artifacts.get("artifacts"), list)
            or artifacts.get("total_count") != len(artifacts["artifacts"])
            or len(artifacts["artifacts"]) > 100):
        raise ValueError("S0_DEPLOY_ARTIFACTS_INCOMPLETE")
    pages = [a for a in artifacts["artifacts"]
             if isinstance(a, dict) and a.get("name") == "github-pages"]
    if (len(pages) != 1 or type(pages[0].get("id")) is not int or pages[0]["id"] < 1
            or pages[0].get("expired") is not False
            or type(pages[0].get("size_in_bytes")) is not int
            or not (0 < pages[0]["size_in_bytes"] <= 100_000_000)
            or not isinstance(pages[0].get("digest"), str)
            or not DIGEST.fullmatch(pages[0]["digest"])):
        raise ValueError("S0_DEPLOY_PAGES_ARTIFACT_INVALID")
    own_run = pages[0].get("workflow_run")
    if isinstance(own_run, dict) and own_run.get("id") != run_id:
        raise ValueError("S0_DEPLOY_ARTIFACT_WRONG_RUN")
    artifact_id = pages[0]["id"]
    events = _lines(log)
    if not events:
        raise ValueError("S0_DEPLOY_EMPTY_LOG")
    # Accept only actual timestamp-prefixed GitHub action output lines in
    # chronological order. A printed command containing this text alone
    # cannot meet the complete ordered sequence.
    expected = (
        "##[group]Run actions/deploy-pages@",
        'Fetching artifact metadata for "github-pages" in this workflow run',
        "Creating Pages deployment with payload:",
        f'"artifact_id": {artifact_id},',
        f'"pages_build_version": "{sha}",',
        f"Created deployment for {sha}, ID: {sha}",
        "Getting Pages deployment status...",
        "Reported success!",
    )
    index = 0
    for item in expected:
        while index < len(events) and item not in events[index]:
            index += 1
        if index == len(events):
            raise ValueError("S0_DEPLOY_RUN_ARTIFACT_OR_SHA_MISMATCH")
        index += 1
    # This confirms precisely which artifact GitHub's own deploy-pages
    # action requested for which sha. Neither deployment nor external
    # publisher identity is independently signed by this check.
    return {
        "status": "GITHUB_DEPLOY_LOG_ARTIFACT_SHA_CORRELATED_NOT_RELEASE",
        "run_id": run_id,
        "run_head_sha": sha,
        "publish_job_id": publishers[0]["id"],
        "pages_artifact_id": artifact_id,
        "artifact_zip_digest": pages[0]["digest"],
        "publish_log_sha256": hashlib.sha256(log).hexdigest(),
        "github_deploy_payload_and_success_seen": True,
        "independent_deployment_identity_attested": False,
        "source_time_or_bookmaker_attested": False,
        "independent_reviewer_approved": False,
        "release_authorized": False,
        "verified_positive_ev": False,
        "production_recommendations": "DISABLED",
    }


def receipt(run: dict, jobs: dict, artifacts: dict, log: bytes) -> dict:
    try:
        return validate(run, jobs, artifacts, log)
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        return {
            "status": "HOLD_DEPLOY_IDENTITY_EVIDENCE_INCOMPLETE",
            "reason": str(exc)[:160],
            "github_deploy_payload_and_success_seen": False,
            "independent_deployment_identity_attested": False,
            "independent_reviewer_approved": False,
            "release_authorized": False,
            "verified_positive_ev": False,
            "production_recommendations": "DISABLED",
        }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True)
    p.add_argument("--jobs", required=True)
    p.add_argument("--artifacts", required=True)
    p.add_argument("--publish-log", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--require-link", action="store_true")
    args = p.parse_args()
    try:
        output = receipt(
            strict_json(_file(args.run, MAX_META)),
            strict_json(_file(args.jobs, MAX_META)),
            strict_json(_file(args.artifacts, MAX_META)),
            _file(args.publish_log, MAX_LOG))
    except (ValueError, TypeError, UnicodeError, OSError) as exc:
        output = {
            "status": "HOLD_DEPLOY_IDENTITY_EVIDENCE_INCOMPLETE",
            "reason": str(exc)[:160],
            "release_authorized": False,
            "verified_positive_ev": False,
            "production_recommendations": "DISABLED",
        }
    Path(args.output).write_text(json.dumps(output, sort_keys=True, indent=2) + "\n",
                                 encoding="utf-8")
    print(json.dumps(output, sort_keys=True))
    if args.require_link and output["status"] != "GITHUB_DEPLOY_LOG_ARTIFACT_SHA_CORRELATED_NOT_RELEASE":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
