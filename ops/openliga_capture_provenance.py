"""Reverify one controlled OpenLigaDB capture; never authenticate publisher truth.

Only this invocation's successful ``gh attestation verify`` stdout supplies
verified certificate identity and Rekor time. Saved verification JSON is ignored.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess

from ops.openliga_capture_pack import validate_capture


REPOSITORY = "CHANCHUNWA1989/football-king-report"
REPOSITORY_URI = "https://github.com/" + REPOSITORY
WORKFLOW_PATH = ".github/workflows/four-model-shadow-daily.yml"
WORKFLOW_URI = REPOSITORY_URI + "/" + WORKFLOW_PATH + "@refs/heads/main"
SUBJECT_NAME, BUNDLE_NAME = "openliga-capture.tar", "capture.sigstore.json"
MAX_TAR_BYTES, MAX_BUNDLE_BYTES, MAX_VERIFICATION_BYTES = 4_000_000, 2_000_000, 4_000_000
SUMMARY_KEYS = ("schema", "status", "production_recommendations", "candidate_only",
                "controlled_capture_content_verified", "origin_chain_scope", "origin_manifest_schema",
                "origin_chain_complete", "manifest_sha256", "manifest_bytes", "source_receipt",
                "raw_sha256", "raw_bytes", "raw_record_count", "captured_utc", "capture_latest_utc",
                "upstream_independence", "raw_source_identity_authenticated",
                "publisher_identity_authenticated", "source_identity_independently_authenticated",
                "upstream_independence_authenticated", "actual_kickoff_authenticated",
                "regulation_ft_authenticated", "outcomes_independently_authenticated",
                "independently_verified", "eligible_for_model_scoring", "eligible_for_betting_promotion",
                "formal_eligible")


class AuditError(ValueError):
    """Public-safe rejection code; never raw input or CLI output."""


def _require(condition, reason):
    if not condition:
        raise AuditError(reason)


def _object(items):
    result = {}
    for key, value in items:
        _require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _bad_constant(_):
    raise AuditError("NONFINITE_JSON_NUMBER")


def _float(value):
    result = float(value)
    _require(math.isfinite(result), "NONFINITE_JSON_NUMBER")
    return result


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_object, parse_constant=_bad_constant, parse_float=_float)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise AuditError("INVALID_JSON") from exc


def _clean_path(path):
    _require(isinstance(path, Path) and ".." not in path.parts, "UNSAFE_PROOF_PATH")
    _require(all(not part.is_symlink() for part in (path.absolute(), *path.absolute().parents)),
             "UNSAFE_PROOF_PATH")


def _read(path, maximum):
    from ops.openliga_capture_pack import _read_regular
    try:
        _clean_path(path)
        return _read_regular(path, maximum)
    except (OSError, ValueError, TypeError) as exc:
        raise AuditError("MISSING_UNSAFE_OR_CHANGED_PROOF_FILE") from exc


def _time(value):
    _require(isinstance(value, str) and 0 < len(value) <= 80, "INVALID_TLOG_TIMESTAMP")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(stamp.tzinfo is not None and stamp.utcoffset() == timedelta(0),
                 "NON_UTC_TLOG_TIMESTAMP")
        return stamp.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError) as exc:
        raise AuditError("INVALID_TLOG_TIMESTAMP") from exc


def _certificate(source, workflow, run_id, attempt):
    return {
        "issuer": "https://token.actions.githubusercontent.com",
        "subjectAlternativeName": WORKFLOW_URI, "buildSignerURI": WORKFLOW_URI,
        "buildConfigURI": WORKFLOW_URI, "githubWorkflowRepository": REPOSITORY,
        "githubWorkflowRef": "refs/heads/main", "githubWorkflowSHA": workflow,
        "sourceRepositoryURI": REPOSITORY_URI, "sourceRepositoryDigest": source,
        "sourceRepositoryRef": "refs/heads/main", "buildSignerDigest": workflow,
        "buildConfigDigest": workflow, "runnerEnvironment": "github-hosted",
        "sourceRepositoryIdentifier": "1411226578",
        "sourceRepositoryOwnerURI": "https://github.com/CHANCHUNWA1989",
        "sourceRepositoryOwnerIdentifier": "339931460",
        "runInvocationURI": REPOSITORY_URI + "/actions/runs/" + run_id + "/attempts/" + attempt,
    }


def _verify(path, bundle_path, bundle, digest, cert, now):
    # No shell, user-selected executable, or replacement GH authentication environment.
    argv = ["gh", "attestation", "verify", str(path), "--bundle", str(bundle_path),
            "--repo", REPOSITORY, "--signer-workflow", REPOSITORY + "/" + WORKFLOW_PATH,
            "--source-ref", "refs/heads/main", "--source-digest", cert["sourceRepositoryDigest"],
            "--signer-digest", cert["buildSignerDigest"], "--deny-self-hosted-runners",
            "--format", "json"]
    try:
        completed = subprocess.run(argv, capture_output=True, shell=False, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuditError("ATTESTATION_TOOL_UNAVAILABLE_OR_TIMEOUT") from exc
    _require(completed.returncode == 0, "ATTESTATION_CLI_REJECTED")
    _require(isinstance(completed.stdout, bytes) and 0 < len(completed.stdout) <= MAX_VERIFICATION_BYTES,
             "EMPTY_OR_OVERSIZED_VERIFICATION_OUTPUT")
    output = _json(completed.stdout)
    _require(isinstance(output, list) and len(output) == 1 and isinstance(output[0], dict),
             "AMBIGUOUS_VERIFICATION_RESULTS")
    item = output[0]
    _require(isinstance(item.get("attestation"), dict)
             and item["attestation"].get("bundle") == bundle, "VERIFIED_BUNDLE_MISMATCH")
    result = item.get("verificationResult")
    _require(isinstance(result, dict) and result.get("mediaType") ==
             "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
             "INVALID_VERIFICATION_RESULT_SCHEMA")
    signature = result.get("signature")
    verified_cert = signature.get("certificate") if isinstance(signature, dict) else None
    _require(isinstance(verified_cert, dict) and all(verified_cert.get(k) == v for k, v in cert.items()),
             "CERTIFICATE_IDENTITY_MISMATCH")
    stamps = result.get("verifiedTimestamps")
    _require(isinstance(stamps, list) and len(stamps) == 1 and isinstance(stamps[0], dict)
             and stamps[0].get("type") == "Tlog" and stamps[0].get("uri") == "https://rekor.sigstore.dev",
             "MISSING_OR_AMBIGUOUS_TRUSTED_TLOG")
    witness = _time(stamps[0].get("timestamp"))
    _require(witness <= now, "FUTURE_TLOG_TIMESTAMP")
    statement = result.get("statement")
    _require(isinstance(statement, dict) and statement.get("_type") == "https://in-toto.io/Statement/v1"
             and statement.get("predicateType") == "https://slsa.dev/provenance/v1",
             "INVALID_VERIFIED_STATEMENT")
    subjects = statement.get("subject")
    _require(isinstance(subjects, list) and len(subjects) == 1 and isinstance(subjects[0], dict)
             and subjects[0].get("name") == SUBJECT_NAME
             and subjects[0].get("digest") == {"sha256": digest}, "VERIFIED_SUBJECT_BYTES_MISMATCH")
    return witness


def audit(proof: Path, *, source_sha, workflow_sha, run_id, attempt, now=None):
    report = {"schema": "football-king-openliga-capture-provenance-v1", "status": "HOLD",
              "production_recommendations": "DISABLED", "audit_completed": False,
              "signature_identity_and_subject_verified": False, "capture_content_replayed": False,
              "raw_source_identity_authenticated": False, "publisher_identity_authenticated": False,
              "source_identity_independently_authenticated": False,
              "upstream_independence_authenticated": False, "actual_kickoff_authenticated": False,
              "regulation_ft_authenticated": False, "formal_eligible": False,
              "outcomes_independently_authenticated": False, "independently_verified": False,
              "eligible_for_model_scoring": False, "eligible_for_betting_promotion": False,
              "notice": "只驗證受控擷取身份、原始位元組與重播；不認證出版者真偽、獨立賽果或預測優勢。"}
    try:
        for value in (source_sha, workflow_sha):
            _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value),
                     "INVALID_TRUSTED_COMMIT")
        for value in (run_id, attempt):
            _require(isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,19}", value),
                     "INVALID_TRUSTED_RUN")
        current = now if now is not None else datetime.now(timezone.utc)
        _require(isinstance(current, datetime) and current.tzinfo is not None, "INVALID_AUDIT_CLOCK")
        current = current.astimezone(timezone.utc)
        _clean_path(proof)
        _require(proof.is_dir(), "INVALID_PROOF_DIRECTORY")
        _require({p.name for p in proof.iterdir()} == {SUBJECT_NAME, BUNDLE_NAME},
                 "PROOF_FILE_ALLOWLIST_MISMATCH")
        raw = _read(proof / SUBJECT_NAME, MAX_TAR_BYTES)
        raw_bundle = _read(proof / BUNDLE_NAME, MAX_BUNDLE_BYTES)
        bundle = _json(raw_bundle)
        _require(isinstance(bundle, dict) and bundle.get("mediaType") ==
                 "application/vnd.dev.sigstore.bundle.v0.3+json"
                 and isinstance(bundle.get("dsseEnvelope"), dict), "INVALID_SIGSTORE_BUNDLE")
        digest = hashlib.sha256(raw).hexdigest()
        witness = _verify(proof / SUBJECT_NAME, proof / BUNDLE_NAME, bundle, digest,
                          _certificate(source_sha, workflow_sha, run_id, attempt), current)
        _require(_read(proof / SUBJECT_NAME, MAX_TAR_BYTES) == raw
                 and _read(proof / BUNDLE_NAME, MAX_BUNDLE_BYTES) == raw_bundle,
                 "PROOF_BYTES_CHANGED_DURING_VERIFICATION")
        try:
            summary = validate_capture(raw, witness=witness, now=current)
        except ValueError as exc:
            raise AuditError("CAPTURE_CONTENT_REPLAY_FAILED") from exc
        _require(isinstance(summary, dict) and summary.get("controlled_capture_content_verified") is True,
                 "CAPTURE_CONTENT_REPLAY_FAILED")
        report.update(audit_completed=True, signature_identity_and_subject_verified=True,
                      capture_content_replayed=True, source_commit=source_sha, workflow_commit=workflow_sha,
                      run_id=run_id, run_attempt=attempt, checked_utc=current.isoformat(),
                      verification_tool="gh attestation verify", verified_tlog_utc=witness.isoformat(),
                      subject_sha256={SUBJECT_NAME: digest},
                      bundle_sha256=hashlib.sha256(raw_bundle).hexdigest(),
                      capture_summary={key: summary[key] for key in SUMMARY_KEYS if key in summary},
                      reason="CONTROLLED_OPENLIGA_CAPTURE_PROVENANCE_VERIFIED")
    except (AuditError, OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        report["reason"] = str(exc) if isinstance(exc, AuditError) else "AUDIT_INPUT_OR_TOOL_ERROR"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", type=Path, required=True)
    for name in ("source-sha", "workflow-sha", "run-id", "attempt"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        _clean_path(args.output)
        _require(not args.output.resolve().is_relative_to(args.proof.resolve()), "UNSAFE_REPORT_OUTPUT")
        protected = [args.proof / SUBJECT_NAME, args.proof / BUNDLE_NAME]
        _require(not args.output.exists() or (stat.S_ISREG(args.output.stat().st_mode)
                 and args.output.stat().st_nlink == 1 and
                 all(not source.exists() or not args.output.samefile(source) for source in protected)),
                 "UNSAFE_REPORT_OUTPUT")
    except (OSError, ValueError):
        parser.error("--output must be a separate regular derived file outside --proof without aliases")
    report = audit(args.proof, source_sha=args.source_sha, workflow_sha=args.workflow_sha,
                   run_id=args.run_id, attempt=args.attempt)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(args.output, flags, 0o600), "w") as stream:
            info = os.fstat(stream.fileno())
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "UNSAFE_REPORT_OUTPUT")
            stream.truncate(0)
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError):
        return 1
    return 0 if report["audit_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
