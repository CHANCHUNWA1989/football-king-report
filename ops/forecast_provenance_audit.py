"""Reverify signed bytes, then audit witness time against RECORDED kickoffs.

Only this invocation's successful ``gh attestation verify`` stdout supplies
certificate identities and verified Rekor timestamps. Saved verification JSON,
predicate times and recorded match times are never independent attestations.
Even a positive observation does not satisfy a production eligibility gate.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess


REPOSITORY = "CHANCHUNWA1989/football-king-report"
REPOSITORY_URI = "https://github.com/" + REPOSITORY
WORKFLOW_PATH = ".github/workflows/football-king-iphone.yml"
WORKFLOW_URI = REPOSITORY_URI + "/" + WORKFLOW_PATH + "@refs/heads/main"
SUBJECT_NAMES = ("shadow.json", "paired.json", "slate.json")
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_VERIFICATION_BYTES = 4 * 1024 * 1024
MAX_COHORT_ROWS = 10000
IDENTITY_FIELDS = ("league", "home", "away", "kickoff_utc", "prediction_utc")


class AuditError(ValueError):
    """An intentional, public-safe rejection code; never raw CLI output."""


def _require(condition, reason):
    if not condition:
        raise AuditError(reason)


def _unique_object(items):
    obj = {}
    for key, value in items:
        _require(key not in obj, "DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def _bad_constant(_):
    raise AuditError("NONFINITE_JSON_NUMBER")


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise AuditError("INVALID_JSON") from exc


def _read(path, maximum):
    _require(isinstance(path, Path) and not path.is_symlink() and path.is_file(),
             "MISSING_OR_UNSAFE_PROOF_FILE")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    _require(0 < len(raw) <= maximum, "PROOF_FILE_SIZE_LIMIT")
    return raw


def _time(value, *, utc_only=False):
    _require(isinstance(value, str) and 0 < len(value) <= 80, "INVALID_TIMESTAMP")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, OverflowError) as exc:
        raise AuditError("INVALID_TIMESTAMP") from exc
    _require(stamp.tzinfo is not None, "NAIVE_TIMESTAMP")
    if utc_only:
        _require(stamp.utcoffset() == timedelta(0), "NON_UTC_TLOG_TIMESTAMP")
    return stamp.astimezone(timezone.utc)


def _text(value):
    return isinstance(value, str) and 0 < len(value) <= 160 and value.isprintable()


def _vector(value):
    _require(isinstance(value, list) and len(value) == 3
             and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1
                     for v in value) and abs(sum(value) - 1) <= .002,
             "INVALID_PROBABILITY_VECTOR")
    return value


def _identity(row):
    _require(isinstance(row, dict) and all(_text(row.get(k)) for k in IDENTITY_FIELDS)
             and row["league"] in LEAGUES and row["home"] != row["away"],
             "INVALID_FIXTURE_IDENTITY")
    return tuple(row[k] for k in IDENTITY_FIELDS)


def _fixture_key(row):
    ident = _identity(row)
    # Exact text matching still links the signed documents. Uniqueness uses
    # normalized time so Z/+00:00 cannot manufacture a second fixture.
    return ident[:3] + (_time(row["kickoff_utc"]).isoformat(),)


def _certificate(expected_source, expected_workflow, run_id, attempt):
    return {
        "issuer": "https://token.actions.githubusercontent.com",
        "subjectAlternativeName": WORKFLOW_URI,
        "buildSignerURI": WORKFLOW_URI, "buildConfigURI": WORKFLOW_URI,
        "githubWorkflowRepository": REPOSITORY,
        "githubWorkflowRef": "refs/heads/main", "githubWorkflowSHA": expected_workflow,
        "sourceRepositoryURI": REPOSITORY_URI,
        "sourceRepositoryDigest": expected_source, "sourceRepositoryRef": "refs/heads/main",
        "buildSignerDigest": expected_workflow, "buildConfigDigest": expected_workflow,
        "runnerEnvironment": "github-hosted", "sourceRepositoryIdentifier": "1411226578",
        "sourceRepositoryOwnerURI": "https://github.com/CHANCHUNWA1989",
        "sourceRepositoryOwnerIdentifier": "339931460",
        "runInvocationURI": REPOSITORY_URI + "/actions/runs/" + run_id + "/attempts/" + attempt,
    }


def _verify(path, bundle_path, bundle, digests, expected_certificate, now):
    # No shell, no user-selected executable, no replacement GH environment.
    argv = ["gh", "attestation", "verify", str(path), "--bundle", str(bundle_path),
            "--repo", REPOSITORY, "--signer-workflow", REPOSITORY + "/" + WORKFLOW_PATH,
            "--source-ref", "refs/heads/main",
            "--source-digest", expected_certificate["sourceRepositoryDigest"],
            "--signer-digest", expected_certificate["buildSignerDigest"],
            "--deny-self-hosted-runners", "--format", "json"]
    try:
        completed = subprocess.run(argv, capture_output=True, shell=False, timeout=30,
                                   check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuditError("ATTESTATION_TOOL_UNAVAILABLE_OR_TIMEOUT") from exc
    _require(completed.returncode == 0, "ATTESTATION_CLI_REJECTED")
    raw = completed.stdout
    _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_VERIFICATION_BYTES,
             "EMPTY_OR_OVERSIZED_VERIFICATION_OUTPUT")
    output = _json(raw)
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
    cert = signature.get("certificate") if isinstance(signature, dict) else None
    _require(isinstance(cert, dict) and all(cert.get(k) == v for k, v in expected_certificate.items()),
             "CERTIFICATE_IDENTITY_MISMATCH")
    stamps = result.get("verifiedTimestamps")
    _require(isinstance(stamps, list) and len(stamps) == 1 and isinstance(stamps[0], dict)
             and stamps[0].get("type") == "Tlog"
             and stamps[0].get("uri") == "https://rekor.sigstore.dev",
             "MISSING_OR_AMBIGUOUS_TRUSTED_TLOG")
    witness = _time(stamps[0].get("timestamp"), utc_only=True)
    _require(witness <= now + timedelta(minutes=5), "FUTURE_TLOG_TIMESTAMP")
    statement = result.get("statement")
    _require(isinstance(statement, dict)
             and statement.get("_type") == "https://in-toto.io/Statement/v1"
             and statement.get("predicateType") == "https://slsa.dev/provenance/v1",
             "INVALID_VERIFIED_STATEMENT")
    subjects = statement.get("subject")
    _require(isinstance(subjects, list) and len(subjects) == 3,
             "WRONG_VERIFIED_SUBJECT_SET")
    found = {}
    for subject in subjects:
        _require(isinstance(subject, dict) and isinstance(subject.get("name"), str)
                 and subject["name"] in SUBJECT_NAMES and subject["name"] not in found
                 and subject.get("digest") == {"sha256": digests[subject["name"]]},
                 "VERIFIED_SUBJECT_BYTES_MISMATCH")
        found[subject["name"]] = subject["digest"]
    # Compare all three successful CLI outputs, without trusting any predicate
    # time or identity field. The certificate and verifiedTimestamps above rule.
    coherence = json.dumps([cert, stamps, statement], sort_keys=True, separators=(",", ":"))
    return witness, coherence


def _documents(raw):
    shadow, paired, slate = (_json(raw[name]) for name in SUBJECT_NAMES)
    _require(all(isinstance(doc, dict) and doc.get("production_recommendations") == "DISABLED"
                 for doc in (shadow, paired, slate)), "UNSAFE_DOCUMENT")
    forecasts, pairs, display = shadow.get("predictions"), paired.get("comparisons"), slate.get("rows")
    _require(shadow.get("schema") == "football-king-uncalibrated-shadow-1"
             and isinstance(forecasts, list)
             and shadow.get("status") == ("SHADOW_ONLY" if forecasts else "HOLD")
             and len(forecasts) <= MAX_COHORT_ROWS
             and type(shadow.get("predictions_count")) is int
             and shadow["predictions_count"] == len(forecasts), "INVALID_SHADOW_DOCUMENT")
    _time(shadow.get("as_of_utc"))
    _require(paired.get("status") in ("HOLD", "RESEARCH_ONLY") and isinstance(pairs, list)
             and len(pairs) <= MAX_COHORT_ROWS and type(paired.get("matched_count")) is int
             and paired["matched_count"] == len(pairs), "INVALID_PAIRED_COHORT")
    _require(slate.get("schema") == "football-king-forward-pick-verification-slate-v1"
             and isinstance(display, list) and len(display) <= 100
             and type(slate.get("verification_rows")) is int
             and slate["verification_rows"] == len(display)
             and type(slate.get("point_in_time_market_pairs")) is int
             and slate["point_in_time_market_pairs"] == len(pairs), "INVALID_SLATE_SUBSET")
    # The upstream zero-prediction snapshot is HOLD, with no possible paired
    # or display cohort. This is still signed material requiring all 3 CLI
    # verifications, never a shortcut around verification for an empty run.
    _require(bool(forecasts) or (paired.get("status") == "HOLD" and not pairs and not display),
             "INCONSISTENT_EMPTY_HOLD_COHORT")
    return shadow, pairs, display


def _case_audit(shadow, pairs, display, witness):
    forecasts = defaultdict(list)
    shadow_fixtures = Counter()
    shadow_events = Counter(row["event_id"] for row in shadow["predictions"]
                            if isinstance(row, dict) and _text(row.get("event_id")))
    for row in shadow["predictions"]:
        try:
            forecasts[_identity(row)].append(row)
            shadow_fixtures[_fixture_key(row)] += 1
        except AuditError:
            continue
    case_counts = Counter(row.get("case_id") for row in pairs
                          if isinstance(row, dict) and _text(row.get("case_id")))
    fixtures = Counter()
    market_events = Counter(row["market_event_id"] for row in pairs
                            if isinstance(row, dict) and _text(row.get("market_event_id")))
    for row in pairs:
        try:
            fixtures[_fixture_key(row)] += 1
        except AuditError:
            continue
    display_by_case = defaultdict(list)
    for row in display:
        _require(isinstance(row, dict) and _text(row.get("case_id"))
                 and row["case_id"] in case_counts, "SLATE_CASE_NOT_IN_COHORT")
        display_by_case[row["case_id"]].append(row)
    cases = []
    for index, row in enumerate(pairs):
        case_id = row.get("case_id") if isinstance(row, dict) else None
        item = {"pair_index": index, "case_id": case_id if _text(case_id) else None,
                "observed_before_recorded_kickoff": False,
                "listed_in_slate": bool(display_by_case.get(case_id)) if _text(case_id) else False}
        try:
            ident = _identity(row)
            _require(_text(case_id), "INVALID_CASE_ID")
            _require(case_counts[case_id] == 1, "DUPLICATE_CASE_ID")
            fixture_key = _fixture_key(row)
            _require(fixtures[fixture_key] == 1, "AMBIGUOUS_PAIRED_FIXTURE")
            _require(_text(row.get("market_event_id"))
                     and market_events[row["market_event_id"]] == 1,
                     "MISSING_OR_AMBIGUOUS_MARKET_EVENT")
            _require(row.get("production_recommendations") == "DISABLED"
                     and row.get("available_for_betting") is False
                     and all(row.get(k) is None for k in ("result", "historical_outcome", "score_ft")),
                     "UNSAFE_OR_RESULT_BEARING_PAIR")
            a, market = _vector(row.get("model")), _vector(row.get("market"))
            candidates = forecasts.get(ident, [])
            _require(len(candidates) == 1, "MISSING_OR_AMBIGUOUS_SHADOW_FORECAST")
            forecast = candidates[0]
            _require(shadow_fixtures[fixture_key] == 1
                     and _text(forecast.get("event_id"))
                     and shadow_events[forecast["event_id"]] == 1,
                     "MISSING_OR_AMBIGUOUS_SHADOW_EVENT")
            _require(forecast.get("production_recommendations") == "DISABLED"
                     and forecast.get("status") in (None, "SCHEDULED")
                     and all(forecast.get(k) is None for k in ("result", "historical_outcome", "score_ft"))
                     and _vector([forecast.get(k) for k in ("p_home", "p_draw", "p_away")]) == a
                     and forecast["prediction_utc"] == shadow["as_of_utc"],
                     "SHADOW_FORECAST_CONFLICT")
            kickoff, prediction, snapshot, updated = (_time(row.get(k)) for k in (
                "kickoff_utc", "prediction_utc", "market_snapshot_utc", "market_updated_utc"))
            _require(updated <= snapshot <= prediction <= witness,
                     "MARKET_FORECAST_WITNESS_CHRONOLOGY_CONFLICT")
            _require(witness <= kickoff - timedelta(minutes=10), "WITNESS_TOO_LATE_FOR_RECORDED_KICKOFF")
            listed = display_by_case.get(case_id, [])
            _require(len(listed) <= 1, "AMBIGUOUS_SLATE_CASE")
            if listed:
                entry = listed[0]
                anchor = hashlib.sha256(json.dumps([
                    case_id, row["league"], row["home"], row["away"], kickoff.isoformat(),
                    prediction.isoformat(), a, market], ensure_ascii=False,
                    separators=(",", ":")).encode()).hexdigest()
                _require(_identity(entry) == ident
                         and entry.get("production_recommendations") == "DISABLED"
                         and _vector(entry.get("model_probabilities_1x2")) == a
                         and _vector(entry.get("earlier_market_consensus_probabilities_1x2")) == market
                         and entry.get("market_snapshot_utc") == row["market_snapshot_utc"]
                         and entry.get("market_updated_utc") == row["market_updated_utc"]
                         and entry.get("sealed_pick_digest") == anchor
                         and entry.get("settled_result") is None, "SLATE_PAIR_CONFLICT")
            item.update(observed_before_recorded_kickoff=True,
                        reason="OBSERVED_BEFORE_RECORDED_KICKOFF",
                        league=row["league"], home=row["home"], away=row["away"],
                        recorded_prediction_utc=prediction.isoformat(),
                        recorded_kickoff_utc=kickoff.isoformat(),
                        verified_tlog_utc=witness.isoformat())
        except AuditError as exc:
            item["reason"] = str(exc)
        cases.append(item)
    return cases


def audit(proof, *, source_sha, workflow_sha, run_id, attempt, now=None):
    """Reverify fixed inputs; never accept a saved *.verification.json as proof."""
    report = {
        "schema": "football-king-forecast-provenance-time-audit-v1",
        "status": "HOLD", "production_recommendations": "DISABLED",
        "audit_completed": False, "signature_identity_and_subjects_verified": False,
        "immutable_forecast_evidence_verified": False,
        "outcomes_independently_authenticated": False,
        "recorded_kickoff_independently_authenticated": False,
        "market_prices_executable": False, "model_advantage_verified": False,
        "eligible_for_betting_promotion": False,
        "observed_before_recorded_kickoff_count": 0, "total_pairs": 0,
        "slate_row_count": 0, "cases": [],
        "notice": ("只核對可信見證早於檔案所記錄開波時間；開波時間仍未獨立認證。"
                   "不認證實際開波、賽果、可成交市場、模型優勢或正式推薦資格。"),
    }
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
        _require(isinstance(proof, Path) and not proof.is_symlink() and proof.is_dir(),
                 "INVALID_PROOF_DIRECTORY")
        report.update(source_commit=source_sha, workflow_commit=workflow_sha,
                      run_id=run_id, run_attempt=attempt, checked_utc=current.isoformat(),
                      verification_tool="gh attestation verify")
        raw = {name: _read(proof / name, MAX_FILE_BYTES) for name in SUBJECT_NAMES}
        bundle_path = proof / "research.sigstore.json"
        raw_bundle = _read(bundle_path, MAX_BUNDLE_BYTES)
        bundle = _json(raw_bundle)
        _require(isinstance(bundle, dict), "INVALID_BUNDLE")
        shadow, pairs, display = _documents(raw)
        report.update(total_pairs=len(pairs), slate_row_count=len(display))
        digests = {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}
        report.update(subject_sha256=digests, bundle_sha256=hashlib.sha256(raw_bundle).hexdigest())
        expected = _certificate(source_sha, workflow_sha, run_id, attempt)
        verified = [_verify(proof / name, bundle_path, bundle, digests, expected, current)
                    for name in SUBJECT_NAMES]
        _require(all(item == verified[0] for item in verified), "INCONSISTENT_VERIFIED_ATTESTATIONS")
        # Detect replacement between the hashed read and the CLI reads.
        _require(all(_read(proof / name, MAX_FILE_BYTES) == raw[name] for name in SUBJECT_NAMES)
                 and _read(bundle_path, MAX_BUNDLE_BYTES) == raw_bundle,
                 "PROOF_BYTES_CHANGED_DURING_VERIFICATION")
        witness = verified[0][0]
        cases = _case_audit(shadow, pairs, display, witness)
        report.update(audit_completed=True, signature_identity_and_subjects_verified=True,
                      verified_tlog_utc=witness.isoformat(), cases=cases,
                      observed_before_recorded_kickoff_count=sum(
                          row["observed_before_recorded_kickoff"] for row in cases),
                      excluded_reason_counts=dict(Counter(row["reason"] for row in cases
                          if not row["observed_before_recorded_kickoff"])),
                      reason="RECORDED_TIME_AUDIT_COMPLETED")
    except (AuditError, OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        report.update(reason=str(exc) if isinstance(exc, AuditError) else "AUDIT_INPUT_OR_TOOL_ERROR",
                      cases=[], observed_before_recorded_kickoff_count=0,
                      audit_completed=False, signature_identity_and_subjects_verified=False)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    # The derived report must never overwrite the signed source material.
    protected = [args.proof / name for name in SUBJECT_NAMES + ("research.sigstore.json",)]
    aliases_input = args.output.exists() and any(
        path.exists() and args.output.samefile(path) for path in protected)
    if (args.output.is_symlink() or args.output.resolve().is_relative_to(args.proof.resolve())
            or aliases_input):
        parser.error("--output must be a separate derived file outside --proof")
    report = audit(args.proof, source_sha=args.source_sha, workflow_sha=args.workflow_sha,
                   run_id=args.run_id, attempt=args.attempt)
    try:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return 1
    return 0 if report["audit_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
