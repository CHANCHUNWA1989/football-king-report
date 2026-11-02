"""Re-verify a private prospective seal against a trusted Sigstore Rekor witness.

This stage does NOT issue attestation certificates, fetch licensed bookmaker
quotes, or count certified forward outcomes. The external operator must pin the
expected GitHub main-branch signer workflow and run using separately trusted
GitHub metadata; anything stored in the proof directory is untrusted.

Only successful *this invocation's* gh attestation verify stdout can establish
a signed seal existed at a Rekor timestamp before the RECORDED kickoff. That
does NOT independently authenticate fixture kickoff, provider data, model
calibration or settlement, and cannot authorize betting.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from private_quote_forward_freeze import (
    FreezeError, verify_freeze, _json_bytes_object,
)
from private_quote_snapshot_receipt import (
    ReceiptError, _read_raw_file, _payload_receipt, _write_private_new,
    _pairs_unique, _nonfinite,
)

REPOSITORY = "CHANCHUNWA1989/football-king-report"
REPO_URI = "https://github.com/" + REPOSITORY
WORKFLOW_PATH = ".github/workflows/football-king-private-seal-attest.yml"
WORKFLOW_URI = REPO_URI + "/" + WORKFLOW_PATH + "@refs/heads/main"
PROOF_FILES = frozenset(("seal.json", "seal.sigstore.json"))
MAX_SEAL_BYTES = 65_536
MAX_BUNDLE_BYTES = 2_000_000
MAX_VERIFY_BYTES = 4_000_000
SHA = re.compile(r"[0-9a-f]{40}\Z")
DECIMAL = re.compile(r"[1-9][0-9]{0,19}\Z")


class AttestationError(ValueError):
    """Fixed non-sensitive reason code; never echo private source or CLI stdout."""


def _require(condition, reason):
    if not condition:
        raise AttestationError(reason)


def _strict_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs_unique,
                          parse_constant=_nonfinite)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise AttestationError("INVALID_ATTESTATION_JSON") from exc


def _time(value):
    _require(type(value) is str and 1 <= len(value) <= 80,
             "INVALID_WITNESS_TIME")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(instant.tzinfo is not None and instant.utcoffset() == timedelta(0),
                 "NON_UTC_WITNESS_TIME")
        return instant.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError) as exc:
        raise AttestationError("INVALID_WITNESS_TIME") from exc


def _path_safe(path):
    _require(type(path) is Path and ".." not in path.parts,
             "UNSAFE_PROOF_PATH")
    # Reject symlinks anywhere along the path, not just leaf.
    _require(all(not p.is_symlink() for p in (path.absolute(), *path.absolute().parents)),
             "UNSAFE_PROOF_PATH")


def _read(path, maximum):
    _path_safe(path)
    try:
        before = path.lstat()
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                 "UNSAFE_PROOF_FILE")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            info = os.fstat(stream.fileno())
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                     and (info.st_ino, info.st_dev) == (before.st_ino, before.st_dev),
                     "PROOF_FILE_CHANGED")
            data = stream.read(maximum + 1)
        _require(0 < len(data) <= maximum, "PROOF_SIZE_LIMIT")
        return data
    except OSError as exc:
        raise AttestationError("UNREADABLE_PROOF_FILE") from exc


def _certificate(source_sha, workflow_sha, run_id, attempt):
    _require(type(source_sha) is str and SHA.fullmatch(source_sha) is not None
             and type(workflow_sha) is str and SHA.fullmatch(workflow_sha) is not None,
             "INVALID_PINNED_COMMIT")
    _require(type(run_id) is str and DECIMAL.fullmatch(run_id) is not None
             and type(attempt) is str and DECIMAL.fullmatch(attempt) is not None,
             "INVALID_PINNED_RUN")
    return {
        "issuer": "https://token.actions.githubusercontent.com",
        "subjectAlternativeName": WORKFLOW_URI,
        "buildSignerURI": WORKFLOW_URI, "buildConfigURI": WORKFLOW_URI,
        "githubWorkflowRepository": REPOSITORY,
        "githubWorkflowRef": "refs/heads/main",
        "githubWorkflowSHA": workflow_sha,
        "sourceRepositoryURI": REPO_URI,
        "sourceRepositoryDigest": source_sha,
        "sourceRepositoryRef": "refs/heads/main",
        "buildSignerDigest": workflow_sha,
        "buildConfigDigest": workflow_sha,
        "runnerEnvironment": "github-hosted",
        "sourceRepositoryIdentifier": "1411226578",
        "sourceRepositoryOwnerURI": "https://github.com/CHANCHUNWA1989",
        "sourceRepositoryOwnerIdentifier": "339931460",
        "runInvocationURI": REPO_URI + "/actions/runs/" + run_id + "/attempts/" + attempt,
    }


def _authenticated_witness(proof, bundle, seal_digest, cert, now):
    # Pinned signer/ref/digest rules are passed to the crypto verifier. Never
    # read verification reports from the proof folder or trust its timestamps.
    command = [
        "gh", "attestation", "verify", str(proof / "seal.json"),
        "--bundle", str(proof / "seal.sigstore.json"),
        "--repo", REPOSITORY,
        "--signer-workflow", REPOSITORY + "/" + WORKFLOW_PATH,
        "--source-ref", "refs/heads/main",
        "--source-digest", cert["sourceRepositoryDigest"],
        "--signer-digest", cert["buildSignerDigest"],
        "--deny-self-hosted-runners", "--format", "json",
    ]
    try:
        completed = subprocess.run(command, shell=False, capture_output=True,
                                   timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AttestationError("ATTESTATION_TOOL_UNAVAILABLE_OR_TIMEOUT") from exc
    _require(completed.returncode == 0, "CRYPTO_VERIFICATION_REJECTED")
    _require(type(completed.stdout) is bytes
             and 0 < len(completed.stdout) <= MAX_VERIFY_BYTES,
             "INVALID_VERIFICATION_OUTPUT")
    items = _strict_json(completed.stdout)
    _require(type(items) is list and len(items) == 1
             and type(items[0]) is dict, "AMBIGUOUS_VERIFICATION_RESULTS")
    item = items[0]
    _require(type(item.get("attestation")) is dict
             and item["attestation"].get("bundle") == bundle,
             "VERIFIED_BUNDLE_MISMATCH")
    result = item.get("verificationResult")
    _require(type(result) is dict
             and result.get("mediaType") ==
             "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
             "INVALID_VERIFIED_RESULT")
    signature = result.get("signature")
    verified_cert = signature.get("certificate") if type(signature) is dict else None
    _require(type(verified_cert) is dict
             and all(verified_cert.get(k) == v for k, v in cert.items()),
             "SIGNER_CERTIFICATE_IDENTITY_MISMATCH")
    stamps = result.get("verifiedTimestamps")
    _require(type(stamps) is list and len(stamps) == 1
             and type(stamps[0]) is dict
             and stamps[0].get("type") == "Tlog"
             and stamps[0].get("uri") == "https://rekor.sigstore.dev",
             "MISSING_TRUSTED_REKOR_TIMESTAMP")
    stamp = _time(stamps[0].get("timestamp"))
    _require(stamp <= now + timedelta(minutes=5), "FUTURE_WITNESS_TIMESTAMP")
    statement = result.get("statement")
    _require(type(statement) is dict
             and statement.get("_type") == "https://in-toto.io/Statement/v1"
             and statement.get("predicateType") == "https://slsa.dev/provenance/v1",
             "INVALID_VERIFIED_STATEMENT")
    _require(statement.get("subject") ==
             [{"name": "seal.json", "digest": {"sha256": seal_digest}}],
             "VERIFIED_SUBJECT_BYTES_MISMATCH")
    return stamp


def audit(proof, raw_odds, receipt, fixture, market, forecast_raw, *,
          source_sha, workflow_sha, run_id, attempt, now=None):
    """Inspect private proof + independently pinned signer, fail closed."""
    report = {
        "schema": "football-king-private-prospective-witness-audit-v1",
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "signature_and_subject_verified": False,
        "seal_semantics_replayed": False,
        "seal_witnessed_before_recorded_kickoff": False,
        "recorded_fixture_kickoff_independently_authenticated": False,
        "bookmaker_quote_independently_authenticated": False,
        "model_leakage_or_calibration_verified": False,
        "certified_independent_forward_samples": 0,
        "eligible_for_model_scoring": False,
        "eligible_for_betting_promotion": False,
    }
    try:
        expected_cert = _certificate(source_sha, workflow_sha, run_id, attempt)
        current = datetime.now(timezone.utc) if now is None else now
        _require(type(current) is datetime and current.tzinfo is not None
                 and current.utcoffset() is not None, "INVALID_AUDIT_CLOCK")
        current = current.astimezone(timezone.utc)
        _require(type(proof) is Path, "UNSAFE_PROOF_PATH")
        _path_safe(proof)
        _require(proof.is_dir() and {p.name for p in proof.iterdir()} == PROOF_FILES,
                 "MISSING_OR_EXTRA_PROOF_FILES")
        seal_raw = _read(proof / "seal.json", MAX_SEAL_BYTES)
        bundle_raw = _read(proof / "seal.sigstore.json", MAX_BUNDLE_BYTES)
        seal = _strict_json(seal_raw)
        bundle = _strict_json(bundle_raw)
        _require(type(seal) is dict and type(bundle) is dict
                 and bundle.get("mediaType") == "application/vnd.dev.sigstore.bundle.v0.3+json"
                 and type(bundle.get("dsseEnvelope")) is dict,
                 "INVALID_BUNDLE_OR_SEAL")
        # Verify every link to the original private odds, native event, exact
        # quarter-line, forecast bytes and caller-claimed time before crypto.
        try:
            replay = verify_freeze(raw_odds, receipt, fixture, market, forecast_raw, seal)
        except (FreezeError, ReceiptError, ValueError, TypeError, OverflowError) as exc:
            raise AttestationError("LOCAL_SEAL_REPLAY_REJECTED") from exc
        _require(replay.get("local_bytes_and_semantics_replayed") is True,
                 "LOCAL_SEAL_REPLAY_REJECTED")
        digest = hashlib.sha256(seal_raw).hexdigest()
        witnessed = _authenticated_witness(proof, bundle, digest, expected_cert, current)
        _require(_read(proof / "seal.json", MAX_SEAL_BYTES) == seal_raw
                 and _read(proof / "seal.sigstore.json", MAX_BUNDLE_BYTES) == bundle_raw,
                 "PROOF_BYTES_CHANGED_DURING_VERIFICATION")
        # Only verified Rekor Tlog time (not caller's JSON) can witness existence.
        # The kickoff is still a SOURCE-RECORDED value, not a trusted sports clock.
        claimed_prediction = _time(seal["prediction_utc_claimed"])
        claimed_capture = _time(receipt["captured_utc_claimed_by_caller"])
        recorded_kickoff = _time(seal["kickoff_utc_claimed"])
        _require(claimed_capture <= claimed_prediction <= witnessed,
                 "CLAIMED_PREDICTION_AFTER_WITNESS")
        _require(witnessed <= recorded_kickoff - timedelta(minutes=10),
                 "WITNESS_AFTER_RECORDED_PREMATCH_CUTOFF")
        report.update(
            signature_and_subject_verified=True,
            seal_semantics_replayed=True,
            seal_witnessed_before_recorded_kickoff=True,
            verified_rekor_timestamp_utc=witnessed.isoformat(),
            seal_sha256=digest,
            signer_source_commit=source_sha,
            signer_workflow_commit=workflow_sha,
            authenticated_run_id=run_id,
            authenticated_attempt=attempt,
            reason="SIGNED_SEAL_EXISTED_BEFORE_RECORDED_KICKOFF_ONLY",
        )
    except (AttestationError, OSError, ValueError, TypeError,
            OverflowError, RecursionError) as exc:
        report["reason"] = str(exc) if isinstance(exc, AttestationError) else "INVALID_PROOF_OR_INPUT"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--raw-odds", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--market", type=Path, required=True)
    parser.add_argument("--forecast", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(
            args.proof, _read_raw_file(args.raw_odds),
            _payload_receipt(_read_raw_file(args.receipt)),
            _json_bytes_object(_read_raw_file(args.fixture)),
            _json_bytes_object(_read_raw_file(args.market)),
            _read_raw_file(args.forecast),
            source_sha=args.source_sha, workflow_sha=args.workflow_sha,
            run_id=args.run_id, attempt=args.attempt,
        )
        _write_private_new(args.output, result)
    except (AttestationError, ReceiptError, FreezeError, OSError,
            ValueError, TypeError, OverflowError) as exc:
        # Print only a fixed error code; never data, path or sensitive CLI stderr.
        print(json.dumps({"status": "HOLD", "reason": "UNSAFE_PRIVATE_PROOF",
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps({"status": "HOLD",
                      "signature_and_subject_verified": result["signature_and_subject_verified"],
                      "certified_independent_forward_samples": 0,
                      "production_recommendations": "DISABLED"}))
    return 0 if result["signature_and_subject_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
