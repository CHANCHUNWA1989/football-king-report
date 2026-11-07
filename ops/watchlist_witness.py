"""Read-only GitHub Sigstore watchlist-digest witness. Research/HOLD only.

Only the current gh attestation verification's trusted Tlog clock may establish
witness time, not saved JSON, user-set clocks or attestation predicates.
"""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops.research_watchlist_review import _manifest_digest, _watchlist, seal_manifest, _time
from ops.research_safe_output import write_new_private_json

REPOSITORY = "CHANCHUNWA1989/football-king-report"
WORKFLOW_PATH = ".github/workflows/research-watchlist-attestation.yml"
WORKFLOW_URI = ("https://github.com/" + REPOSITORY + "/" + WORKFLOW_PATH +
                "@refs/heads/main")
SUBJECT = "watchlist-manifest-sha256.txt"
BUNDLE = "watchlist.sigstore.json"


class WitnessError(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise WitnessError(reason)


def _load(path, maximum):
    _require(path.is_file() and not path.is_symlink(), "MISSING_OR_UNSAFE_WITNESS_FILE")
    with path.open("rb") as f:
        raw = f.read(maximum + 1)
    _require(0 < len(raw) <= maximum, "WITNESS_FILE_SIZE_LIMIT")
    return raw


def _no_duplicate_keys(pairs):
    output = {}
    for k, v in pairs:
        _require(k not in output, "DUPLICATE_WITNESS_JSON_KEY")
        output[k] = v
    return output


def _bad_constant(_):
    raise WitnessError("NONFINITE_WITNESS_JSON")


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_no_duplicate_keys,
                          parse_constant=_bad_constant)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise WitnessError("INVALID_WITNESS_JSON") from exc


def audit(watchlist, pin, *, proof_dir, source_sha, workflow_sha,
          run_id, attempt, now=None):
    report = {
        "schema": "football-king-watchlist-witness-audit-v1",
        "status": "HOLD", "production_recommendations": "DISABLED",
        "audit_completed": False, "signature_subject_and_tlog_verified": False,
        "observed_before_recorded_kickoff": False,
        "actual_kickoff_independently_authenticated": False,
        "bookmaker_quote_source_verified": False,
        "results_independently_verified": False,
        "model_out_of_sample_validated": False,
        "main_branch_governance_independently_verified": False,
        "eligible_for_betting_promotion": False,
        "notice": "只驗證 GitHub 身份、名單摘要與透明日誌早於記錄的開波；實際開波及盤口未認證。",
    }
    try:
        _require(all(isinstance(x, str) and re.fullmatch("[0-9a-f]{40}", x)
                     for x in (source_sha, workflow_sha)), "INVALID_PINNED_SOURCE_COMMIT")
        _require(all(isinstance(x, str) and re.fullmatch("[1-9][0-9]{0,19}", x)
                     for x in (run_id, attempt)), "INVALID_PINNED_RUN")
        current = now if now is not None else datetime.now(timezone.utc)
        _require(isinstance(current, datetime) and current.tzinfo is not None
                 and current.utcoffset() is not None, "INVALID_VERIFICATION_CLOCK")
        current = current.astimezone(timezone.utc)
        _require(isinstance(proof_dir, Path) and proof_dir.is_dir()
                 and not proof_dir.is_symlink(), "INVALID_WITNESS_DIRECTORY")
        _require(isinstance(pin, dict) and isinstance(pin.get("issued_at_utc"), str),
                 "WATCHLIST_PIN_MISMATCH")
        cohort = _watchlist(watchlist, current)
        _require(bool(cohort), "EMPTY_WATCHLIST")
        expected = seal_manifest(watchlist, issued_at_utc=pin["issued_at_utc"])
        # Type-sensitive canonical equality: bool is not interchangeable with int.
        _require(json.dumps(pin, sort_keys=True, separators=(",", ":"), allow_nan=False)
                 == json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False),
                 "WATCHLIST_PIN_MISMATCH")
        issued = _time(pin["issued_at_utc"])
        _require(issued <= current, "FUTURE_LOCAL_PIN")
        digest = _manifest_digest(watchlist)
        subject = _load(proof_dir / SUBJECT, 256)
        _require(subject == (digest + "\n").encode("ascii"),
                 "SIGNED_MANIFEST_DIGEST_MISMATCH")
        bundle = _json(_load(proof_dir / BUNDLE, 2_000_000))
        _require(isinstance(bundle, dict), "INVALID_SIGSTORE_BUNDLE")
        cmd = [
            "gh", "attestation", "verify", str(proof_dir / SUBJECT),
            "--bundle", str(proof_dir / BUNDLE), "--repo", REPOSITORY,
            "--signer-workflow", REPOSITORY + "/" + WORKFLOW_PATH,
            "--source-ref", "refs/heads/main", "--source-digest", source_sha,
            "--signer-digest", workflow_sha, "--deny-self-hosted-runners",
            "--format", "json",
        ]
        try:
            execution = subprocess.run(cmd, capture_output=True, timeout=30,
                                       shell=False, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise WitnessError("ATTESTATION_TOOL_UNAVAILABLE_OR_TIMEOUT") from exc
        _require(execution.returncode == 0, "ATTESTATION_CLI_REJECTED")
        raw = execution.stdout
        _require(isinstance(raw, bytes) and 0 < len(raw) <= 4_000_000,
                 "INVALID_VERIFICATION_OUTPUT_SIZE")
        verified = _json(raw)
        _require(isinstance(verified, list) and len(verified) == 1
                 and isinstance(verified[0], dict), "AMBIGUOUS_ATTESTATION_OUTPUT")
        item = verified[0]
        _require(isinstance(item.get("attestation"), dict)
                 and item["attestation"].get("bundle") == bundle,
                 "ATTESTATION_BUNDLE_MISMATCH")
        result = item.get("verificationResult")
        _require(isinstance(result, dict)
                 and result.get("mediaType") ==
                 "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
                 "INVALID_VERIFICATION_RESULT")
        signature = result.get("signature")
        certificate = signature.get("certificate") if isinstance(signature, dict) else None
        expected_cert = {
            "issuer": "https://token.actions.githubusercontent.com",
            "subjectAlternativeName": WORKFLOW_URI,
            "githubWorkflowRepository": REPOSITORY,
            "githubWorkflowRef": "refs/heads/main",
            "githubWorkflowSHA": workflow_sha,
            "sourceRepositoryURI": "https://github.com/" + REPOSITORY,
            "sourceRepositoryDigest": source_sha,
            "sourceRepositoryRef": "refs/heads/main",
            "runnerEnvironment": "github-hosted",
            "buildSignerURI": WORKFLOW_URI,
            "buildSignerDigest": workflow_sha,
            "runInvocationURI": ("https://github.com/" + REPOSITORY +
                                 "/actions/runs/" + run_id + "/attempts/" + attempt),
        }
        _require(isinstance(certificate, dict)
                 and all(certificate.get(k) == v for k, v in expected_cert.items()),
                 "CERTIFICATE_OR_WORKFLOW_IDENTITY_MISMATCH")
        stamps = result.get("verifiedTimestamps")
        _require(isinstance(stamps, list) and len(stamps) == 1
                 and isinstance(stamps[0], dict) and stamps[0].get("type") == "Tlog"
                 and stamps[0].get("uri") == "https://rekor.sigstore.dev",
                 "MISSING_TRUSTED_TRANSPARENCY_TIMESTAMP")
        raw_stamp = stamps[0].get("timestamp")
        witness = _time(raw_stamp)
        _require(raw_stamp.endswith(("+00:00", "Z"))
                 and witness <= current + timedelta(minutes=5),
                 "INVALID_TRUSTED_TIMESTAMP")
        statement = result.get("statement")
        _require(isinstance(statement, dict)
                 and statement.get("_type") == "https://in-toto.io/Statement/v1"
                 and statement.get("predicateType") == "https://slsa.dev/provenance/v1",
                 "WRONG_ATTESTATION_PREDICATE")
        subjects = statement.get("subject")
        _require(isinstance(subjects, list) and len(subjects) == 1
                 and isinstance(subjects[0], dict)
                 and subjects[0].get("name") == SUBJECT
                 and subjects[0].get("digest") ==
                 {"sha256": hashlib.sha256(subject).hexdigest()},
                 "ATTESTED_SUBJECT_MISMATCH")
        report.update(audit_completed=True, signature_subject_and_tlog_verified=True,
                      witness_tlog_utc=witness.isoformat(), signed_manifest_sha256=digest,
                      signed_selection_count=len(cohort), source_commit=source_sha,
                      signer_commit=workflow_sha, run_id=run_id, attempt=attempt)
        if witness < issued:
            report["reason"] = "WITNESS_BEFORE_PIN_ISSUED"
        elif witness > min(row["kickoff"] for row in cohort) - timedelta(minutes=10):
            report["reason"] = "WITNESS_TOO_LATE_FOR_RECORDED_KICKOFF"
        else:
            report.update(observed_before_recorded_kickoff=True,
                          reason="SIGNED_MANIFEST_BEFORE_RECORDED_KICKOFF_ONLY")
    except (WitnessError, ValueError, KeyError, TypeError, OverflowError,
            OSError, RecursionError, UnicodeError, AttributeError) as exc:
        report["reason"] = str(exc) if isinstance(exc, WitnessError) else (
            "WATCHLIST_PIN_MISMATCH" if isinstance(exc, ValueError)
            else "WITNESS_INPUT_OR_TOOL_ERROR")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--watchlist", type=Path, required=True)
    parser.add_argument("--pin", type=Path, required=True)
    parser.add_argument("--proof-dir", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.is_symlink() or args.output.resolve().is_relative_to(
            args.proof_dir.resolve()):
        parser.error("OUTPUT_CANNOT_OVERWRITE_SIGNED_PROOF")
    for source in (args.watchlist, args.pin):
        if source.is_file() and args.output.exists() and args.output.samefile(source):
            parser.error("OUTPUT_CANNOT_OVERWRITE_INPUT")
    report = audit(
        json.loads(args.watchlist.read_text(encoding="utf-8")),
        json.loads(args.pin.read_text(encoding="utf-8")),
        proof_dir=args.proof_dir, source_sha=args.source_sha,
        workflow_sha=args.workflow_sha, run_id=args.run_id,
        attempt=args.attempt,
    )
    # Do not overwrite a previous witness report, pin, source or alias.
    # Exclusive create also enforces owner-only private permissions.
    write_new_private_json(args.output, report)
    print(json.dumps({"status": "HOLD",
                      "signature_subject_and_tlog_verified":
                      report["signature_subject_and_tlog_verified"],
                      "production_recommendations": "DISABLED"}))
    return 0 if report["signature_subject_and_tlog_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
