"""Reverify pre-kickoff fixture manifest bytes through GitHub/Sigstore.

Only a FRESH successful 'gh attestation verify' invocation can establish the
Tlog witness. Submitted registered_at_utc, saved verification JSON and git
author/committer timestamps are NOT independent clocks. A signed source map
does NOT prove that source IDs, fixture kickoff, odds or corners are true.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

REPOSITORY = "CHANCHUNWA1989/football-king-report"
REPO_URI = "https://github.com/" + REPOSITORY
WORKFLOW_PATH = ".github/workflows/football-king-live-fixture-seal.yml"
WORKFLOW_URI = REPO_URI + "/" + WORKFLOW_PATH + "@refs/heads/main"
MANIFEST_NAME = "fixture-manifest.json"
BUNDLE_NAME = "fixture-manifest.sigstore.json"
MAX_MANIFEST_BYTES = 64_000
MAX_BUNDLE_BYTES = 2_000_000
MAX_CLI_STDOUT_BYTES = 4_000_000


class WitnessError(ValueError):
    """Public-safe error code, no raw signed data or CLI errors."""


def _need(condition, code):
    if not condition:
        raise WitnessError(code)


def _timestamp(value):
    _need(type(value) is str and 0 < len(value) <= 80, "INVALID_WITNESS_TIMESTAMP")
    try:
        time = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        raise WitnessError("INVALID_WITNESS_TIMESTAMP") from None
    _need(time.tzinfo is not None and time.utcoffset() is not None,
          "NAIVE_WITNESS_TIMESTAMP")
    return time.astimezone(timezone.utc)


def _unique_object(pairs):
    out = {}
    for key, value in pairs:
        _need(key not in out, "DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _bad_constant(_value):
    raise WitnessError("INVALID_JSON_CONSTANT")


def _parse_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique_object,
                          parse_constant=_bad_constant)
    except WitnessError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise WitnessError("INVALID_JSON") from None


def _read(proof, filename, limit):
    _need(isinstance(proof, Path) and proof.is_dir() and not proof.is_symlink(),
          "INVALID_PROOF_DIRECTORY")
    path = proof / filename
    _need(path.is_file() and not path.is_symlink(), "MISSING_OR_UNSAFE_PROOF_FILE")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    _need(0 < len(raw) <= limit, "PROOF_SIZE_LIMIT")
    return raw


def validate_manifest(document, *, now=None):
    """Validate a source map; return recorded kickoff, not authenticated kickoff."""
    _need(type(document) is dict and set(document) == {
        "event_id", "kickoff_utc", "registered_at_utc", "source_events"},
        "INVALID_FIXTURE_MANIFEST_SCHEMA")
    event_id = document["event_id"]
    _need(type(event_id) is str and re.fullmatch(r"[a-zA-Z0-9_.:-]{1,128}", event_id) is not None,
          "INVALID_FIXTURE_EVENT_ID")
    kickoff, registered = _timestamp(document["kickoff_utc"]), _timestamp(document["registered_at_utc"])
    _need(registered <= kickoff - timedelta(minutes=10), "CLAIMED_REGISTERED_TIME_TOO_LATE")
    if now is not None:
        _need(kickoff > now + timedelta(minutes=10), "RECORDED_KICKOFF_NOT_FUTURE")
    channels = document["source_events"]
    _need(type(channels) is dict and set(channels) == {"score", "stats", "quote"},
          "INVALID_FIXTURE_SOURCE_CHANNELS")
    for channel in ("score", "stats", "quote"):
        row = channels[channel]
        _need(type(row) is dict and set(row) == {
            "source", "source_event_id", "source_url"}, "INVALID_FIXTURE_SOURCE_SCHEMA")
        for key in ("source", "source_event_id"):
            value = row[key]
            _need(type(value) is str and re.fullmatch(r"[a-zA-Z0-9_.:-]{1,128}", value) is not None,
                  "INVALID_FIXTURE_SOURCE_ID")
        url = row["source_url"]
        _need(type(url) is str and 0 < len(url) <= 2048, "INVALID_FIXTURE_SOURCE_URL")
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme == "https" and parsed.hostname
                     and parsed.username is None and parsed.password is None
                     and parsed.port is None and not parsed.fragment)
        except ValueError:
            valid = False
        _need(bool(valid), "INVALID_FIXTURE_SOURCE_URL")
    return kickoff, registered


def _certificate(source_sha, workflow_sha, run_id, attempt):
    return {
        "issuer": "https://token.actions.githubusercontent.com",
        "subjectAlternativeName": WORKFLOW_URI,
        "buildSignerURI": WORKFLOW_URI,
        "buildConfigURI": WORKFLOW_URI,
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


def audit(proof, *, source_sha, workflow_sha, run_id, attempt, now=None):
    """Return research-only result after real gh verification; fail closed."""
    result = {
        "schema": "football-king-live-fixture-tlog-witness-v1",
        "status": "HOLD", "production_recommendations": "DISABLED",
        "sigstore_tlog_witness_verified": False,
        "manifest_bytes_identity_bound": False,
        "witness_before_recorded_kickoff": False,
        "recorded_kickoff_independently_authenticated": False,
        "provider_events_independently_authenticated": False,
        "upstream_quote_executable_verified": False,
        "model_probability_calibrated": False,
        "certified_positive_ev": False,
        "eligible_for_model_scoring": False,
        "eligible_for_betting_promotion": False,
    }
    try:
        _need(isinstance(proof, Path) and type(source_sha) is str
              and re.fullmatch(r"[a-f0-9]{40}", source_sha) is not None
              and type(workflow_sha) is str
              and re.fullmatch(r"[a-f0-9]{40}", workflow_sha) is not None
              and type(run_id) is str and re.fullmatch(r"[1-9][0-9]{0,19}", run_id) is not None
              and type(attempt) is str and re.fullmatch(r"[1-9][0-9]{0,4}", attempt) is not None,
              "INVALID_PINNED_GITHUB_CONTEXT")
        current = datetime.now(timezone.utc) if now is None else now
        _need(type(current) is datetime and current.tzinfo is not None
              and current.utcoffset() is not None, "INVALID_AUDIT_TIME")
        current = current.astimezone(timezone.utc)
        manifest_raw = _read(proof, MANIFEST_NAME, MAX_MANIFEST_BYTES)
        bundle_raw = _read(proof, BUNDLE_NAME, MAX_BUNDLE_BYTES)
        manifest = _parse_json(manifest_raw)
        bundle = _parse_json(bundle_raw)
        _need(type(bundle) is dict, "INVALID_SIGSTORE_BUNDLE")
        kickoff, registered = validate_manifest(manifest)
        argv = ["gh", "attestation", "verify", str(proof / MANIFEST_NAME),
                "--bundle", str(proof / BUNDLE_NAME),
                "--repo", REPOSITORY, "--signer-workflow",
                REPOSITORY + "/" + WORKFLOW_PATH,
                "--source-ref", "refs/heads/main",
                "--source-digest", source_sha,
                "--signer-digest", workflow_sha,
                "--deny-self-hosted-runners", "--format", "json"]
        try:
            completed = subprocess.run(argv, capture_output=True, shell=False,
                                       timeout=30, check=False)
        except (OSError, subprocess.SubprocessError):
            raise WitnessError("ATTESTATION_TOOL_UNAVAILABLE_OR_TIMEOUT") from None
        _need(completed.returncode == 0, "ATTESTATION_CLI_REJECTED")
        stdout = completed.stdout
        _need(type(stdout) is bytes and 0 < len(stdout) <= MAX_CLI_STDOUT_BYTES,
              "INVALID_VERIFIER_OUTPUT_SIZE")
        response = _parse_json(stdout)
        _need(type(response) is list and len(response) == 1 and type(response[0]) is dict,
              "AMBIGUOUS_VERIFICATION_RESULTS")
        item = response[0]
        _need(type(item.get("attestation")) is dict
              and item["attestation"].get("bundle") == bundle,
              "VERIFIED_BUNDLE_MISMATCH")
        verification = item.get("verificationResult")
        _need(type(verification) is dict and verification.get("mediaType") ==
              "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
              "INVALID_VERIFIER_RESULT")
        signature = verification.get("signature")
        cert = signature.get("certificate") if type(signature) is dict else None
        expected = _certificate(source_sha, workflow_sha, run_id, attempt)
        _need(type(cert) is dict and all(cert.get(k) == v for k, v in expected.items()),
              "CERTIFICATE_IDENTITY_MISMATCH")
        stamps = verification.get("verifiedTimestamps")
        _need(type(stamps) is list and len(stamps) == 1
              and type(stamps[0]) is dict
              and stamps[0].get("type") == "Tlog"
              and stamps[0].get("uri") == "https://rekor.sigstore.dev",
              "MISSING_OR_AMBIGUOUS_TRUSTED_TLOG")
        witness = _timestamp(stamps[0].get("timestamp"))
        _need(witness <= current + timedelta(minutes=5), "FUTURE_TRUSTED_WITNESS")
        statement = verification.get("statement")
        _need(type(statement) is dict
              and statement.get("_type") == "https://in-toto.io/Statement/v1"
              and statement.get("predicateType") == "https://slsa.dev/provenance/v1",
              "INVALID_VERIFIED_STATEMENT")
        subjects = statement.get("subject")
        digest = hashlib.sha256(manifest_raw).hexdigest()
        _need(type(subjects) is list and len(subjects) == 1
              and type(subjects[0]) is dict
              and subjects[0].get("name") == MANIFEST_NAME
              and subjects[0].get("digest") == {"sha256": digest},
              "VERIFIED_SUBJECT_BYTES_MISMATCH")
        _need(registered <= witness, "REGISTERED_AFTER_TRUSTED_WITNESS")
        _need(witness <= kickoff - timedelta(minutes=10),
              "TRUSTED_WITNESS_NOT_PRE_KICKOFF")
        result.update(status="RESEARCH_ONLY",
                      sigstore_tlog_witness_verified=True,
                      manifest_bytes_identity_bound=True,
                      witness_before_recorded_kickoff=True,
                      manifest_sha256=digest,
                      verified_tlog_utc=witness.isoformat(),
                      reason="WITNESS_VERIFIED_RECORDED_KICKOFF_ONLY")
    except (WitnessError, OSError, ValueError, TypeError, OverflowError,
            RecursionError, KeyError, AttributeError) as exc:
        result["reason"] = str(exc) if isinstance(exc, WitnessError) else "WITNESS_INPUT_OR_TOOL_ERROR"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    args = parser.parse_args(argv)
    result = audit(args.proof, source_sha=args.source_sha, workflow_sha=args.workflow_sha,
                   run_id=args.run_id, attempt=args.attempt)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
