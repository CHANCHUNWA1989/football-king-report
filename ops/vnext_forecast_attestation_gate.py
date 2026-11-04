"""VNext PR-07: reverify an externally witnessed PR-06 forecast seal.

Structural tests can mock gh stdout, but ONLY the *fresh* real
"gh attestation verify" command could authenticate a GitHub-signed subject.
This sidecar never declares result/source rights, real performance or EV.
No source fetch or attestation issuing happens here.
"""
import hashlib
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops import ndr_capture_provenance as original_capture
from vnext_prospective_local_seal import read_forecast_seal
from vnext_shadow_forward_audit import _clock, _sha

SCHEMA = "football-king-vnext-forecast-witness-gate-v1"
REPO = "CHANCHUNWA1989/football-king-report"
REPO_URI = "https://github.com/" + REPO
SIGNER_WORKFLOW = ".github/workflows/football-king-vnext-forecast-attest.yml"
SIGNER_URI = REPO_URI + "/" + SIGNER_WORKFLOW + "@refs/heads/main"
MAX_BUNDLE_BYTES = 2_000_000
MAX_VERIFIED_STDOUT_BYTES = 4_000_000
SHA1_COMMIT = re.compile(r"[0-9a-f]{40}\\Z")


def _hold(reason):
    return {
        "schema": SCHEMA, "status": "HOLD",
        "reason": reason if isinstance(reason, str) and len(reason) < 128
                  else "WITNESS_VERIFICATION_REJECTED",
        "signed_seal_bytes_verified": False,
        "external_forecast_time_witness_verified": False,
        "source_license_verified": False, "source_independence_verified": False,
        "actual_kickoff_verified": False, "result_truth_verified": False,
        "model_scoring_eligible": False, "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def _positive_int(value):
    return type(value) is int and 1 <= value <= 10**15


def _safe_time(value):
    value = _clock(value)
    return value


def _pinned_cert(source_commit, workflow_commit, run_id, attempt):
    # Use identity only from GitHub-attested certificate, NOT from predicate.
    return {
        "issuer": "https://token.actions.githubusercontent.com",
        "subjectAlternativeName": SIGNER_URI,
        "buildSignerURI": SIGNER_URI, "buildConfigURI": SIGNER_URI,
        "githubWorkflowRepository": REPO,
        "githubWorkflowRef": "refs/heads/main",
        "githubWorkflowSHA": workflow_commit,
        "sourceRepositoryURI": REPO_URI,
        "sourceRepositoryDigest": source_commit,
        "sourceRepositoryRef": "refs/heads/main",
        "buildSignerDigest": workflow_commit,
        "buildConfigDigest": workflow_commit,
        "runnerEnvironment": "github-hosted",
        "sourceRepositoryIdentifier": "1411226578",
        "sourceRepositoryOwnerURI": "https://github.com/CHANCHUNWA1989",
        "sourceRepositoryOwnerIdentifier": "339931460",
        "runInvocationURI": REPO_URI + "/actions/runs/" + str(run_id)
                            + "/attempts/" + str(attempt),
    }


def verify_witness(root, file_name, *, expected_sha256, bundle_path,
                   source_commit, workflow_commit, run_id, attempt,
                   checked_utc=None):
    """Require exact subject, trusted signer and Rekor time before kickoff-10m.

    All paths remain local; bundle is untrusted until gh verifies it. The
    signer workflow is a *future* trusted producer requirement: it has not
    been executed here, and no actual signed PR-06 forecast is claimed.
    """
    if (not _sha(expected_sha256) or
            any(type(v) is not str or not SHA1_COMMIT.fullmatch(v)
                for v in (source_commit, workflow_commit)) or
            not _positive_int(run_id) or not _positive_int(attempt)):
        raise ValueError("INVALID_PINNED_VERIFICATION_CONTEXT")
    current = _safe_time(checked_utc) if checked_utc is not None else datetime.now(timezone.utc)
    # Identity and digest must come from verified *local* PR-06 seal bytes.
    seal = read_forecast_seal(root, file_name, expected_sha256=expected_sha256)
    path = Path(root) / file_name
    raw = original_capture._read(path, 65536)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("SUBJECT_BYTES_CHANGED")
    raw_bundle = original_capture._read(Path(bundle_path), MAX_BUNDLE_BYTES)
    bundle = original_capture._json(raw_bundle)
    if not isinstance(bundle, dict):
        raise ValueError("INVALID_ATTESTATION_BUNDLE")
    # No shell and no caller-selected workflow/executable, trusted root or
    # substituted GH environment/host. Require signer from main only.
    command = [
        "gh", "attestation", "verify", str(path),
        "--bundle", str(bundle_path), "--repo", REPO,
        "--signer-workflow", REPO + "/" + SIGNER_WORKFLOW,
        "--source-ref", "refs/heads/main",
        "--source-digest", source_commit,
        "--signer-digest", workflow_commit,
        "--deny-self-hosted-runners", "--format", "json",
    ]
    try:
        completed = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=30, shell=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("GH_VERIFIER_UNAVAILABLE_OR_TIMEOUT") from exc
    if completed.returncode != 0:
        raise ValueError("GH_ATTESTATION_VERIFICATION_FAILED")
    stdout = completed.stdout
    if type(stdout) is not bytes or not 0 < len(stdout) <= MAX_VERIFIED_STDOUT_BYTES:
        raise ValueError("INVALID_VERIFICATION_OUTPUT_SIZE")
    verified = original_capture._json(stdout)
    if type(verified) is not list or len(verified) != 1 or type(verified[0]) is not dict:
        raise ValueError("AMBIGUOUS_VERIFICATION_OUTPUT")
    entry = verified[0]
    if type(entry.get("attestation")) is not dict or entry["attestation"].get("bundle") != bundle:
        raise ValueError("VERIFIED_BUNDLE_MISMATCH")
    proof = entry.get("verificationResult")
    if type(proof) is not dict or proof.get("mediaType") != (
            "application/vnd.sigstore.verificationresult+json;version=0.1"):
        # GitHub CLI has historically emitted a vnd.dev.sigstore prefix.
        # Both known, typed media formats are allowed; nothing arbitrary.
        if type(proof) is not dict or proof.get("mediaType") != (
                "application/vnd.dev.sigstore.verificationresult+json;version=0.1"):
            raise ValueError("UNKNOWN_VERIFIED_STATEMENT_FORMAT")
    signature = proof.get("signature")
    certificate = signature.get("certificate") if type(signature) is dict else None
    expected = _pinned_cert(source_commit, workflow_commit, run_id, attempt)
    if type(certificate) is not dict or any(certificate.get(k) != v for k, v in expected.items()):
        raise ValueError("SIGNER_CERTIFICATE_IDENTITY_MISMATCH")
    stamps = proof.get("verifiedTimestamps")
    if type(stamps) is not list or len(stamps) != 1 or type(stamps[0]) is not dict:
        raise ValueError("NO_SINGLE_VERIFIED_TRANSPARENCY_WITNESS")
    if stamps[0].get("type") != "Tlog" or stamps[0].get("uri") != "https://rekor.sigstore.dev":
        raise ValueError("WRONG_TRANSPARENCY_WITNESS")
    witnessed_at = _safe_time(stamps[0].get("timestamp"))
    if witnessed_at > current + timedelta(minutes=5):
        raise ValueError("FUTURE_OR_UNTRUSTED_WITNESS_TIME")
    statement = proof.get("statement")
    if type(statement) is not dict or statement.get("_type") != "https://in-toto.io/Statement/v1":
        raise ValueError("INVALID_VERIFIED_STATEMENT")
    if statement.get("predicateType") != "https://slsa.dev/provenance/v1":
        raise ValueError("INVALID_VERIFIED_PREDICATE_TYPE")
    subjects = statement.get("subject")
    if (type(subjects) is not list or len(subjects) != 1
            or type(subjects[0]) is not dict
            or subjects[0].get("name") != file_name
            or subjects[0].get("digest") != {"sha256": expected_sha256}):
        raise ValueError("SIGNED_SUBJECT_NAME_OR_HASH_MISMATCH")
    kickoff = _safe_time(seal["pair"]["kickoff_utc"])
    as_of = _safe_time(seal["pair"]["as_of_utc"])
    captured = _safe_time(seal["recorded_at_utc"])
    if not as_of <= captured <= witnessed_at <= kickoff - timedelta(minutes=10):
        raise ValueError("WITNESS_AFTER_PREMATCH_CUTOFF_OR_BEFORE_CAPTURE")
    return {
        "schema": SCHEMA, "status": "WITNESSED_BYTES_RESEARCH",
        "fixture_id": seal["pair"]["fixture_id"],
        "forecast_as_of_utc": as_of.isoformat(),
        "subject_sha256": expected_sha256,
        "subject_name": file_name,
        "witness_utc": witnessed_at.isoformat(),
        "source_commit": source_commit,
        "workflow_commit": workflow_commit,
        "github_run_id": run_id,
        "github_run_attempt": attempt,
        "signed_seal_bytes_verified": True,
        "external_forecast_time_witness_verified": True,
        "source_license_verified": False, "source_independence_verified": False,
        "actual_kickoff_verified": False, "result_truth_verified": False,
        "model_scoring_eligible": False, "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def audit_witness(root, file_name, **kwargs):
    try:
        return verify_witness(root, file_name, **kwargs)
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as exc:
        return _hold(str(exc) or "WITNESS_VERIFICATION_REJECTED")
