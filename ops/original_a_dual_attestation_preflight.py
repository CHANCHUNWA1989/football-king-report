"""Future-approved MAIN-only Sigstore/Rekor preflight for A+raw same-GET links.

Never signs, uploads, contacts providers, or changes production. It requires
fresh gh attestation verify of TWO distinct original byte subjects under the
exact same expected future-approved main workflow identity. No corresponding
production signer is enabled by this research PR, so a current real positive
is NOT claimed. All results, including successful cryptographic verification,
remain HOLD/DISABLED: neither publisher truth nor actual kickoff is certified.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .original_a_same_get_shadow_pair import (
    _read_regular, _read_json, _private_directory, _sha, _time, _raw_subject, replay,
)
from .original_a_same_get_private_seal import check_private_bundle

REPOSITORY = "CHANCHUNWA1989/football-king-report"
REPO_URI = "https://github.com/" + REPOSITORY
WORKFLOW_PATH = ".github/workflows/football-king-a-same-get-provenance.yml"
WORKFLOW_URI = REPO_URI + "/" + WORKFLOW_PATH + "@refs/heads/main"
SCHEMA = "football-king-original-a-dual-signature-preflight-v1"
MAX_BUNDLE = 2_000_000
MAX_STDOUT = 4_000_000
BUFFER = timedelta(minutes=10)
SIGNATURE_NAMES = ("source.sigstore.json", "link.sigstore.json")


def _hold(reason, **extra):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "audit_completed": False,
        "exact_main_signer_identity_and_two_subjects_verified": False,
        "fresh_source_rekor_witness_verified": False,
        "fresh_a_link_rekor_witness_verified": False,
        "source_publisher_authenticated": False,
        "actual_kickoff_independently_authenticated": False,
        "training_data_rights_verified": False,
        "eligible_for_model_scoring": False,
        "certified_prospective_samples": 0, "positive_ev_verified": False,
        "model_promoted": False, **extra,
    }


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _strict_json(raw):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            _require(k not in out, "DUPLICATE_PROOF_JSON_KEY")
            out[k] = v
        return out
    def no_nonfinite(_):
        raise ValueError("NONFINITE_PROOF_JSON")
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=no_nonfinite)


def _expected_cert(source_sha, workflow_sha, run_id, attempt):
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


def _reverify(path, bundle_path, *, source_sha, workflow_sha, run_id, attempt, now):
    blob = _read_regular(bundle_path, limit=MAX_BUNDLE)
    bundle = _strict_json(blob)
    _require(type(bundle) is dict and
             bundle.get("mediaType") == "application/vnd.dev.sigstore.bundle.v0.3+json"
             and type(bundle.get("dsseEnvelope")) is dict,
             "INVALID_SIGSTORE_BUNDLE")
    digest = hashlib.sha256(_read_regular(path, limit=8_100_000)).hexdigest()
    cert = _expected_cert(source_sha, workflow_sha, run_id, attempt)
    args = [
        "gh", "attestation", "verify", str(path), "--bundle", str(bundle_path),
        "--repo", REPOSITORY, "--signer-workflow",
        REPOSITORY + "/" + WORKFLOW_PATH,
        "--source-ref", "refs/heads/main", "--source-digest", source_sha,
        "--signer-digest", workflow_sha, "--deny-self-hosted-runners",
        "--format", "json",
    ]
    try:
        done = subprocess.run(args, capture_output=True, shell=False,
                              timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("TRUSTED_GH_VERIFY_UNAVAILABLE") from exc
    _require(done.returncode == 0, "ATTESTATION_CLI_REJECTED")
    _require(type(done.stdout) is bytes and 0 < len(done.stdout) <= MAX_STDOUT,
             "MISSING_OR_OVERSIZED_CLI_VERIFICATION")
    result = _strict_json(done.stdout)
    _require(type(result) is list and len(result) == 1
             and type(result[0]) is dict, "AMBIGUOUS_GH_VERIFICATION")
    item = result[0]
    _require(type(item.get("attestation")) is dict
             and item["attestation"].get("bundle") == bundle,
             "VERIFIED_BUNDLE_NOT_THE_SUPPLIED_BUNDLE")
    verified = item.get("verificationResult")
    _require(type(verified) is dict and verified.get("mediaType") ==
             "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
             "INVALID_VERIFICATION_RESULT_SCHEMA")
    signature = verified.get("signature")
    found_cert = signature.get("certificate") if type(signature) is dict else None
    _require(type(found_cert) is dict
             and all(found_cert.get(k) == v for k, v in cert.items()),
             "UNAPPROVED_OR_NON_MAIN_SIGNER_IDENTITY")
    stamps = verified.get("verifiedTimestamps")
    _require(type(stamps) is list and len(stamps) == 1
             and type(stamps[0]) is dict
             and stamps[0].get("type") == "Tlog"
             and stamps[0].get("uri") == "https://rekor.sigstore.dev",
             "MISSING_REAL_REKOR_WITNESS")
    witness_raw = stamps[0].get("timestamp")
    # Verified Tlog stamps must carry explicit UTC, not a local offset
    # chosen by any archive metadata or test fixture.
    _require(type(witness_raw) is str and
             (witness_raw.endswith("Z") or witness_raw.endswith("+00:00")),
             "NON_UTC_REKOR_WITNESS")
    witnessed = _time(witness_raw)
    _require(witnessed <= now, "FUTURE_OR_UNTRUSTED_REKOR_WITNESS")
    statement = verified.get("statement")
    _require(type(statement) is dict
             and statement.get("_type") == "https://in-toto.io/Statement/v1"
             and statement.get("predicateType") == "https://slsa.dev/provenance/v1",
             "INVALID_VERIFIED_PROVENANCE_STATEMENT")
    subjects = statement.get("subject")
    _require(type(subjects) is list and len(subjects) == 1
             and type(subjects[0]) is dict
             and subjects[0].get("name") == path.name
             and subjects[0].get("digest") == {"sha256": digest},
             "SIGNED_SUBJECT_BYTES_MISMATCH")
    _require(_read_regular(path, limit=8_100_000) is not None
             and hashlib.sha256(_read_regular(path, limit=8_100_000)).hexdigest()
             == digest
             and _read_regular(bundle_path, limit=MAX_BUNDLE) == blob,
             "VERIFIED_BYTES_CHANGED_DURING_AUDIT")
    return witnessed


def audit(*, original_dir, pair_file, proof_dir, original_sha,
          pair_sha, source_sha, workflow_sha, source_run, source_attempt,
          link_run, link_attempt, now=None):
    """Two independent CLI invocations, strict chronological candidate only."""
    report = _hold("ATTESTED_MAIN_SOURCE_AND_LINK_SUBJECTS_UNAVAILABLE")
    try:
        for v in (source_sha, workflow_sha):
            _require(type(v) is str and re.fullmatch("[0-9a-f]{40}", v),
                     "INVALID_TRUSTED_MAIN_COMMIT")
        for v in (source_run, source_attempt, link_run, link_attempt):
            _require(type(v) is str and re.fullmatch("[1-9][0-9]{0,19}", v),
                     "INVALID_TRUSTED_RUN_ID")
        _require((source_run, source_attempt) != (link_run, link_attempt),
                 "SAME_RUN_CANNOT_ESTABLISH_SEPARATE_PRIOR_WITNESS")
        _require(_sha(original_sha) and _sha(pair_sha), "INVALID_SUBJECT_DIGEST")
        current = datetime.now(timezone.utc) if now is None else now
        _require(type(current) is datetime and current.tzinfo is not None
                 and current.utcoffset() is not None, "INVALID_VERIFIER_CLOCK")
        current = current.astimezone(timezone.utc)
        original_dir = _private_directory(original_dir)
        proof_dir = _private_directory(proof_dir)
        pair_file = Path(pair_file)
        _private_directory(pair_file.parent)
        _require({x.name for x in proof_dir.iterdir()} == set(SIGNATURE_NAMES),
                 "PROOF_BUNDLE_ALLOWLIST_MISMATCH")
        original_file = original_dir / (original_sha + ".openliga-private.tar")
        _require(pair_file.name == pair_sha + ".a-source-link-private.tar",
                 "INVALID_PAIR_SUBJECT_IDENTITY")
        # A valid local pairing is a prerequisite; don't pay for CLI or
        # trust a signed blob without exact original raw/forecast replay.
        local = replay(pair_file, original_dir=original_dir,
                       source_bundle_sha256=original_sha,
                       expected_pair_sha256=pair_sha)
        _require(local.get("locally_replayable_byte_identity") is True
                 and local.get("status") == "HOLD",
                 "INVALID_LOCAL_SOURCE_AND_A_LINK")
        import io
        import tarfile
        raw_pair = _read_regular(pair_file, limit=2_200_000)
        with tarfile.open(fileobj=io.BytesIO(raw_pair), mode="r:") as t:
            link = _strict_json(t.extractfile("link.json").read(100_001))
        _require(link.get("source_bundle_sha256_unattested") == original_sha,
                 "LINK_DOES_NOT_REFERENCE_EXACT_SOURCE")
        fixtures = link.get("fixtures")
        _require(type(fixtures) is list and len(fixtures) > 0,
                 "EMPTY_OR_UNTRUSTED_A_FORECAST_LINK")
        claimed_a = _time(link["a_batch_completed_utc_claimed"])
        claimed_source = _time(link["source_capture_utc_claimed"])
        _require(claimed_source <= claimed_a,
                 "SOURCE_CAPTURE_AFTER_CLAIMED_A")
        kickoff_bound = min(_time(f["kickoff_utc"]) for f in fixtures)
        witness_source = _reverify(
            original_file, proof_dir / SIGNATURE_NAMES[0],
            source_sha=source_sha, workflow_sha=workflow_sha,
            run_id=source_run, attempt=source_attempt, now=current)
        _require(claimed_source <= witness_source <= claimed_a,
                 "SOURCE_REKOR_NOT_BEFORE_RECORDED_A_COMPLETION")
        # The source bundle also carries an untrusted local seal-completion
        # clock. An actual Rekor witness cannot precede the completed exact
        # bytes it signed. Checking this catches inconsistent staged metadata.
        source_meta, _ = _raw_subject(
            _read_regular(original_file, limit=8_100_000),
            link["source_raw_sha256_unattested"])
        _require(_time(source_meta["local_sealed_utc_unattested"]) <= witness_source,
                 "SOURCE_REKOR_BEFORE_LOCAL_SOURCE_SEAL")
        witness_link = _reverify(
            pair_file, proof_dir / SIGNATURE_NAMES[1],
            source_sha=source_sha, workflow_sha=workflow_sha,
            run_id=link_run, attempt=link_attempt, now=current)
        _require(claimed_a <= witness_link
                 and witness_source <= witness_link
                 and witness_link <= kickoff_bound - BUFFER,
                 "A_LINK_REKOR_NOT_BEFORE_RECORDED_KICKOFF")
        report = _hold(
            "TWO_MAIN_SUBJECTS_REVERIFIED_BEFORE_RECORDED_KICKOFF_NOT_PRODUCTION_ELIGIBLE",
            audit_completed=True,
            exact_main_signer_identity_and_two_subjects_verified=True,
            fresh_source_rekor_witness_verified=True,
            fresh_a_link_rekor_witness_verified=True,
            source_witness_utc=witness_source.isoformat(),
            a_link_witness_utc=witness_link.isoformat(),
            recorded_first_kickoff_utc=kickoff_bound.isoformat(),
            matched_local_native_fixture_count=len(fixtures),
            source_subject_sha256=original_sha,
            a_link_subject_sha256=pair_sha,
            note=("Trusted GitHub/rekoR witness proves signed SUBJECT bytes existed "
                  "by those verification times. This does NOT independently "
                  "authenticate actual kickoff, upstream OpenLigaDB truth, "
                  "model-input legal rights, odds, xG, score, OOS or EV."),
        )
    except Exception as exc:
        # Public-safe failure result. In particular never leak subprocess stderr
        # or raw private subject bytes from exceptions.
        code = str(exc) if type(exc) is ValueError else "DUAL_PROOF_INPUT_OR_TOOL_REJECTED"
        report = _hold(code if len(code) <= 110 else "DUAL_PROOF_INPUT_OR_TOOL_REJECTED")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("original-dir", "pair-file", "proof-dir", "original-sha",
                 "pair-sha", "source-sha", "workflow-sha",
                 "source-run", "source-attempt", "link-run", "link-attempt"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    r = audit(original_dir=args.original_dir, pair_file=args.pair_file,
              proof_dir=args.proof_dir, original_sha=args.original_sha,
              pair_sha=args.pair_sha, source_sha=args.source_sha,
              workflow_sha=args.workflow_sha,
              source_run=args.source_run, source_attempt=args.source_attempt,
              link_run=args.link_run, link_attempt=args.link_attempt)
    print(json.dumps(r, ensure_ascii=False, sort_keys=True))
    return 0 if r["audit_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
