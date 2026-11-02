"""Read-only official GitHub Actions run identity gate for private Sigstore seals.

Only HTTPS bytes obtained directly from GitHub's FIXED repository API can pin
the signer source/workflow SHA and workflow_dispatch run attempt. User-provided
JSON, CI artifacts, README links, or saved "verified" files are NOT anchors.
The public GitHub API is read-only and may rate-limit: on failure we HOLD.
This does not authenticate proprietary quote origin, kickoff, or positive EV.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import ssl
import urllib.error
import urllib.request

from private_quote_seal_attestation import (
    AttestationError, REPOSITORY, WORKFLOW_PATH, _certificate, _time,
    _require, _read, audit,
)
from private_quote_forward_freeze import _json_bytes_object
from private_quote_snapshot_receipt import (
    _pairs_unique, _nonfinite, _payload_receipt, _write_private_new,
)

SCHEMA = "football-king-official-sigstore-run-handoff-v1"
BASE_URL = "https://api.github.com/repos/" + REPOSITORY + "/actions/runs/"
REPOSITORY_ID = 1411226578
MAX_RUN_METADATA_BYTES = 131072
MAX_RAW_ODDS_BYTES = 2_000_000
MAX_LOCAL_BYTES = 65_536


class OfficialRunError(ValueError):
    """Only fixed, non-secret reason codes."""


def _fail(reason):
    raise OfficialRunError(reason)


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _fail("OFFICIAL_RUN_REDIRECT_REJECTED")


def _fetch_official_run(run_id):
    """Never accept caller-supplied endpoint or cached metadata."""
    try:
        _certificate("0" * 40, "0" * 40, run_id, "1")
    except AttestationError as exc:
        raise OfficialRunError("INVALID_OFFICIAL_RUN_ID") from exc
    url = BASE_URL + run_id
    request = urllib.request.Request(
        url, method="GET",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "football-king-private-seal-run-verifier",
            "Cache-Control": "no-store",
        },
    )
    try:
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            _NoRedirects(),
        )
        with opener.open(request, timeout=8) as response:
            if (response.status != 200 or response.geturl() != url):
                _fail("UNTRUSTED_RUN_ENDPOINT")
            raw = response.read(MAX_RUN_METADATA_BYTES + 1)
    except (urllib.error.URLError, OSError, TimeoutError, ssl.SSLError) as exc:
        if isinstance(exc, OfficialRunError):
            raise
        raise OfficialRunError("GITHUB_RUN_UNAVAILABLE") from exc
    if not 0 < len(raw) <= MAX_RUN_METADATA_BYTES:
        _fail("INVALID_GITHUB_RUN_RESPONSE_SIZE")
    try:
        result = json.loads(raw, object_pairs_hook=_pairs_unique,
                            parse_constant=_nonfinite)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise OfficialRunError("INVALID_GITHUB_RUN_JSON") from exc
    if type(result) is not dict:
        _fail("INVALID_GITHUB_RUN_DOCUMENT")
    return result


def validate_official_run(run, *, run_id, attempt, now=None):
    """Shape and chronology checks only. Caller MUST NOT treat JSON as trusted.

    Used solely on _fetch_official_run() HTTPS response, never on user files.
    """
    try:
        _certificate("0" * 40, "0" * 40, run_id, attempt)
    except AttestationError as exc:
        raise OfficialRunError("INVALID_OFFICIAL_RUN_PIN") from exc
    if type(run) is not dict or type(run.get("id")) is not int:
        _fail("INVALID_OFFICIAL_RUN_DOCUMENT")
    if (str(run["id"]) != run_id or type(run.get("run_attempt")) is not int
            or str(run["run_attempt"]) != attempt):
        _fail("MISMATCHED_RUN_OR_ATTEMPT")
    for key in ("repository", "head_repository"):
        record = run.get(key)
        if (type(record) is not dict or type(record.get("id")) is not int
                or record["id"] != REPOSITORY_ID
                or record.get("full_name") != REPOSITORY):
            _fail("RUN_FROM_OTHER_REPOSITORY")
    if (run.get("event") != "workflow_dispatch"
            or run.get("head_branch") != "main"
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("path") not in (
                WORKFLOW_PATH,
                WORKFLOW_PATH + "@refs/heads/main",
            )):
        _fail("UNTRUSTED_SIGNER_WORKFLOW_RUN")
    sha = run.get("head_sha")
    try:
        _certificate(sha, sha, run_id, attempt)
        started = _time(run["run_started_at"])
        created = _time(run["created_at"])
        updated = _time(run["updated_at"])
    except (AttestationError, KeyError, TypeError, ValueError) as exc:
        raise OfficialRunError("INVALID_GITHUB_RUN_CHRONOLOGY") from exc
    current = datetime.now(timezone.utc) if now is None else now
    if type(current) is not datetime or current.tzinfo is None:
        _fail("INVALID_VERIFIER_CLOCK")
    current = current.astimezone(timezone.utc)
    if not (created <= started <= updated <= current + timedelta(minutes=5)):
        _fail("INVALID_GITHUB_RUN_CHRONOLOGY")
    return {
        "source_sha": sha,
        "workflow_sha": sha,
        "run_id": run_id,
        "attempt": attempt,
        "run_started_utc": started,
        "run_finished_utc": updated,
    }


def audit_official_run(proof, raw_odds, receipt, fixture, market, forecast_raw, *,
                       run_id, attempt, now=None):
    """No security promotion without independent live GitHub run identity."""
    result = {
        "schema": SCHEMA, "status": "HOLD",
        "official_run_metadata_https_verified": False,
        "signature_and_subject_verified": False,
        "seal_witnessed_before_recorded_kickoff": False,
        "bookmaker_quote_independently_authenticated": False,
        "recorded_fixture_kickoff_independently_authenticated": False,
        "certified_independent_forward_samples": 0,
        "eligible_for_betting_promotion": False,
        "production_recommendations": "DISABLED",
    }
    try:
        raw_run = _fetch_official_run(run_id)
        pin = validate_official_run(raw_run, run_id=run_id, attempt=attempt, now=now)
        result["official_run_metadata_https_verified"] = True
        proof_result = audit(
            proof, raw_odds, receipt, fixture, market, forecast_raw,
            source_sha=pin["source_sha"], workflow_sha=pin["workflow_sha"],
            run_id=pin["run_id"], attempt=pin["attempt"], now=now,
        )
        result["signature_and_subject_verified"] = (
            proof_result.get("signature_and_subject_verified") is True)
        if result["signature_and_subject_verified"]:
            witnessed = _time(proof_result["verified_rekor_timestamp_utc"])
            if not pin["run_started_utc"] <= witnessed <= (
                    pin["run_finished_utc"] + timedelta(minutes=5)):
                _fail("SIGNED_WITNESS_OUTSIDE_GITHUB_RUN")
            result["seal_witnessed_before_recorded_kickoff"] = (
                proof_result.get("seal_witnessed_before_recorded_kickoff") is True)
            result["verified_rekor_timestamp_utc"] = witnessed.isoformat()
            result["signed_seal_sha256"] = proof_result["seal_sha256"]
            result["verified_github_source_sha"] = pin["source_sha"]
            result["verified_github_run_id"] = run_id
            result["verified_github_attempt"] = attempt
        else:
            result["reason"] = proof_result.get("reason", "SIGNED_PROOF_REJECTED")
        if result["seal_witnessed_before_recorded_kickoff"]:
            result["reason"] = "SIGNATURE_WITNESSED_BEFORE_SOURCE_RECORDED_KICKOFF_ONLY"
    except (OfficialRunError, AttestationError, OSError, KeyError, TypeError,
            ValueError, OverflowError) as exc:
        # On any late-stage rejection, revoke earlier observations.
        result["signature_and_subject_verified"] = False
        result["seal_witnessed_before_recorded_kickoff"] = False
        result.pop("verified_rekor_timestamp_utc", None)
        result.pop("signed_seal_sha256", None)
        result.pop("verified_github_source_sha", None)
        result.pop("verified_github_run_id", None)
        result.pop("verified_github_attempt", None)
        result["reason"] = str(exc) if isinstance(exc, OfficialRunError) else "INDEPENDENT_WITNESS_REJECTED"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--raw-odds", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--market", type=Path, required=True)
    parser.add_argument("--forecast", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_official_run(
            args.proof, _read(args.raw_odds, MAX_RAW_ODDS_BYTES),
            _payload_receipt(_read(args.receipt, MAX_LOCAL_BYTES)),
            _json_bytes_object(_read(args.fixture, MAX_LOCAL_BYTES)),
            _json_bytes_object(_read(args.market, MAX_LOCAL_BYTES)),
            _read(args.forecast, MAX_LOCAL_BYTES),
            run_id=args.run_id, attempt=args.attempt,
        )
        _write_private_new(args.output, result)
    except (OfficialRunError, OSError, ValueError, TypeError,
            AttestationError, OverflowError) as exc:
        print(json.dumps({"status": "HOLD", "reason": "UNSAFE_PRIVATE_PROOF",
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps({
        "status": "HOLD",
        "github_run_identity_verified": result["official_run_metadata_https_verified"],
        "seal_witnessed_before_recorded_kickoff":
            result["seal_witnessed_before_recorded_kickoff"],
        "certified_independent_forward_samples": 0,
        "production_recommendations": "DISABLED",
    }))
    return 0 if result["seal_witnessed_before_recorded_kickoff"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
