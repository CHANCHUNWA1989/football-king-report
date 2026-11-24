"""Bind pinned original forecasts to raw bytes inside a freshly verified capture.

Four fresh CLI checks establish controlled byte provenance only. Source truth,
independence, actual kickoff, regulation FT and outcome admission remain absent.
Run with PYTHONPATH=ops python -m ops.controlled_case_intake.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile

import raw_openligadb_identity_linkage as linkage
from ops import openliga_capture_pack as capture_pack
from ops import openliga_capture_provenance as capture_provenance
from ops import trusted_result_evidence


BLOCKERS = (
    'SCOPE_SPECIFIC_SOURCE_USE_EVIDENCE_MISSING',
    'PUBLISHER_IDENTITY_NOT_INDEPENDENTLY_AUTHENTICATED',
    'INDEPENDENT_UPSTREAM_COLLECTION_EVIDENCE_MISSING',
    'INDEPENDENT_RESULT_SOURCE_MISSING',
    'CROSS_SOURCE_FIXTURE_MAPPING_MISSING',
    'ACTUAL_KICKOFF_EVIDENCE_MISSING',
    'REGULATION_RESULT_NOT_INDEPENDENTLY_AUTHENTICATED',
    'FORECAST_PRE_ACTUAL_KICKOFF_ORDER_NOT_AUTHENTICATED',
    'TRUSTED_RESULT_ADMISSION_NOT_IMPLEMENTED',
)


def _require(condition, reason):
    if not condition:
        raise linkage.LinkageError(reason)


def _case_result(selected, original, records, season, source_completed):
    _require(len(selected) == 1 and selected[0].get('fixed_id_linked') is True,
             'PINNED_CASE_MISSING_AMBIGUOUS_OR_CONFLICTING')
    case = selected[0]
    index = case.get('raw_index')
    _require(type(index) is int and 0 <= index < len(records), 'INVALID_LINKED_RAW_INDEX')
    source = records[index]
    _require(len(original) == 1 and original[0].get('league') == 'bundesliga',
             'FORECAST_OUTSIDE_PINNED_SOURCE_POLICY')
    kickoff = linkage._utc(original[0].get('kickoff_utc'), 'INVALID_RECORDED_KICKOFF')
    _require(season == 2026
             and datetime(2026, 7, 1, tzinfo=timezone.utc) <= kickoff
             < datetime(2027, 7, 1, tzinfo=timezone.utc)
             and source.get('leagueShortcut') == 'bl1' and type(source.get('leagueSeason')) is int
             and source['leagueSeason'] == season, 'CAPTURE_FIXTURE_SCOPE_MISMATCH')
    blockers = list(BLOCKERS)
    if source.get('matchIsFinished') is True:
        # The captured score cannot describe regulation play if its own
        # response was already complete before 90 minutes could elapse.
        _require(source_completed >= kickoff + timedelta(minutes=90),
                 'SOURCE_RESPONSE_BEFORE_MINIMUM_REGULATION_END')
        finals = [row for row in source.get('matchResults', [])
                  if type(row) is dict and row.get('resultTypeID') == 2]
        _require(case.get('ft_candidate') is True and len(finals) == 1
                 and finals[0].get('resultTypeKind') == 'After90Minutes',
                 'EXPLICIT_REGULATION_FINAL_CANDIDATE_REQUIRED')
    else:
        blockers.append('NO_REGULATION_FINAL_CANDIDATE')
    return {'intake_completed': True, 'controlled_capture_to_forecast_link_verified': True,
            'case': case, 'blockers': blockers, 'reason': 'CONTROLLED_CAPTURE_BYTES_LINKED_TO_PINNED_FORECAST'}


def _audit(forecast_proof, capture_proof, *, forecast_source_sha, forecast_workflow_sha,
           forecast_run_id, forecast_attempt, capture_source_sha, capture_workflow_sha,
           capture_run_id, capture_attempt, case_ids, paired_sha256, single, now=None):
    schema = ('football-king-controlled-case-intake-v1' if single
              else 'football-king-controlled-cohort-intake-v1')
    report = {**linkage._safety(), 'schema': schema,
              'intake_completed': False, 'controlled_capture_signature_reverified': False,
              'forecast_signature_reverified': False,
              'controlled_capture_to_forecast_link_verified': False,
              'certified_case_count': 0, 'blockers': list(BLOCKERS),
              'derived_review_not_a_trust_input': True,
              'notice': '只連結已驗受控原件與原預測；不是獨立賽果認證或正式推薦入口。'}
    if single:
        report['case'] = None
    else:
        report.update(cases=[], linked_case_count=0)
    try:
        current = datetime.now(timezone.utc) if now is None else now
        _require(isinstance(current, datetime) and current.tzinfo is not None, 'INVALID_INTAKE_CLOCK')
        current = current.astimezone(timezone.utc)
        _require(type(case_ids) in (list, tuple)
                 and 1 <= len(case_ids) <= linkage.forecast_provenance_audit.MAX_COHORT_ROWS,
                 'INVALID_COHORT_SIZE')
        for value in (*case_ids, paired_sha256):
            _require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'INVALID_CASE_PIN')
        _require(len(set(case_ids)) == len(case_ids), 'DUPLICATE_CASE_PIN')
        for folder in (forecast_proof, capture_proof):
            capture_provenance._clean_path(folder)
            _require(folder.is_dir(), 'MISSING_PROOF_DIRECTORY')
        _require(not (forecast_proof.resolve().is_relative_to(capture_proof.resolve())
                      or capture_proof.resolve().is_relative_to(forecast_proof.resolve())),
                 'OVERLAPPING_PROOF_DIRECTORIES')
        paired = linkage._read(forecast_proof / 'paired.json', linkage.forecast_provenance_audit.MAX_FILE_BYTES)
        _require(hashlib.sha256(paired).hexdigest() == paired_sha256, 'PINNED_PAIRED_DIGEST_MISMATCH')
        policy = trusted_result_evidence._policy()
        capture = capture_provenance.audit(
            capture_proof, source_sha=capture_source_sha, workflow_sha=capture_workflow_sha,
            run_id=capture_run_id, attempt=capture_attempt, now=current)
        _require(capture.get('audit_completed') is True
                 and capture.get('signature_identity_and_subject_verified') is True
                 and capture.get('capture_content_replayed') is True,
                 'FRESH_CAPTURE_VERIFICATION_FAILED')
        raw_tar = capture_provenance._read(capture_proof / capture_provenance.SUBJECT_NAME,
                                           capture_provenance.MAX_TAR_BYTES)
        bundle = capture_provenance._read(capture_proof / capture_provenance.BUNDLE_NAME,
                                          capture_provenance.MAX_BUNDLE_BYTES)
        _require(capture.get('subject_sha256') == {
            capture_provenance.SUBJECT_NAME: hashlib.sha256(raw_tar).hexdigest()}
            and capture.get('bundle_sha256') == hashlib.sha256(bundle).hexdigest(),
            'CAPTURE_BYTES_CHANGED_AFTER_FRESH_VERIFICATION')
        witness = capture_provenance._time(capture.get('verified_tlog_utc'))
        replay = capture_pack.validate_capture(raw_tar, witness=witness, now=current)
        capture_pack._same(capture.get('capture_summary'),
                           {key: replay[key] for key in capture_provenance.SUMMARY_KEYS if key in replay},
                           'CAPTURE_SUMMARY_CHANGED_AFTER_FRESH_VERIFICATION')
        files = capture_pack._members(raw_tar)
        report['controlled_capture_signature_reverified'] = True
        # No caller raw-dir, saved audits, tar extraction paths, or second-provider raw.
        with tempfile.TemporaryDirectory(prefix='controlled-case-raw-') as temporary:
            raw_dir = Path(temporary)
            for name in ('manifest.json', 'openligadb.json'):
                with (raw_dir / name).open('xb') as stream:
                    stream.write(files[name])
            linked = linkage.audit_linkage(
                raw_dir, forecast_proof, source_sha=forecast_source_sha,
                workflow_sha=forecast_workflow_sha, run_id=forecast_run_id,
                attempt=forecast_attempt, now=current)
        _require(linked.get('audit_completed') is True and linked.get('forecast_signature_reverified') is True,
                 'FRESH_FORECAST_LINKAGE_FAILED')
        _require(linked.get('paired_sha256') == paired_sha256, 'PINNED_PAIRED_CHANGED_DURING_INTAKE')
        _require(linked.get('raw_sha256') == replay['raw_sha256']
                 and linked.get('manifest_sha256') == replay['manifest_sha256'],
                 'LINKAGE_BYTES_DIFFER_FROM_VERIFIED_CAPTURE')
        _require(capture_provenance._read(capture_proof / capture_provenance.SUBJECT_NAME,
                                         capture_provenance.MAX_TAR_BYTES) == raw_tar
                 and capture_provenance._read(capture_proof / capture_provenance.BUNDLE_NAME,
                                             capture_provenance.MAX_BUNDLE_BYTES) == bundle,
                 'CAPTURE_BYTES_CHANGED_DURING_FORECAST_LINKAGE')
        report['forecast_signature_reverified'] = True
        records = linkage._json(files['openligadb.json'])
        manifest = capture_pack._json(files['manifest.json'])
        source_completed = linkage._utc(replay['source_receipt']['completed_utc'],
                                        'INVALID_SOURCE_RESPONSE_COMPLETED_UTC')
        pairs = linkage._json(paired).get('comparisons', [])
        requested = set(case_ids)
        by_id, originals = defaultdict(list), defaultdict(list)
        for rows, index in ((linked['cases'], by_id), (pairs, originals)):
            for row in rows:
                case_id = row.get('case_id') if type(row) is dict else None
                if type(case_id) is str and case_id in requested:
                    index[case_id].append(row)
        verdicts = []
        for case_id in case_ids:
            verdict = {**linkage._safety(), 'case_id': case_id, 'certified_case_count': 0}
            try:
                verdict.update(_case_result(by_id[case_id], originals[case_id], records,
                                            manifest['season_start'], source_completed))
            except linkage.LinkageError as exc:
                if single:
                    raise
                verdict.update(intake_completed=False, controlled_capture_to_forecast_link_verified=False,
                               case=None, blockers=[*BLOCKERS, str(exc)], reason=str(exc))
            verdicts.append(verdict)
        report.update(
            checked_utc=current.isoformat(), paired_sha256=paired_sha256,
            raw_sha256=replay['raw_sha256'], manifest_sha256=replay['manifest_sha256'],
            forecast_reference=linked['provenance_reference'],
            capture_reference={key: capture[key] for key in (
                'source_commit', 'workflow_commit', 'run_id', 'run_attempt', 'verified_tlog_utc',
                'subject_sha256', 'bundle_sha256')},
            claimed_raw_capture_utc=replay['captured_utc'],
            claimed_source_response_completed_utc=replay['source_receipt']['completed_utc'],
            source_policy={'id': policy['policy_id'], 'sha256': trusted_result_evidence.POLICY_SHA256,
                           'scope': policy['scope'], 'provider': 'OpenLigaDB',
                           'upstream_relationship': policy['providers']['OpenLigaDB']['upstream_relationship'],
                           'public_raw_reuse': policy['providers']['OpenLigaDB']['public_raw_reuse']})
        report['capture_reference'].update(raw_sha256=replay['raw_sha256'],
                                           manifest_sha256=replay['manifest_sha256'])
        if single:
            report.update(verdicts[0])
        else:
            linked_count = sum(item['intake_completed'] for item in verdicts)
            report.update(intake_completed=True, linked_case_count=linked_count,
                          controlled_capture_to_forecast_link_verified=linked_count > 0,
                          cases=verdicts, reason='CONTROLLED_COHORT_INTAKE_COMPLETED')
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        report.update(intake_completed=False, controlled_capture_to_forecast_link_verified=False,
                      reason=str(exc) if isinstance(exc, linkage.LinkageError)
                      else 'CONTROLLED_INTAKE_INPUT_OR_PROOF_REJECTED')
    return report


def audit_case(forecast_proof, capture_proof, *, forecast_source_sha, forecast_workflow_sha,
               forecast_run_id, forecast_attempt, capture_source_sha, capture_workflow_sha,
               capture_run_id, capture_attempt, case_id, paired_sha256, now=None):
    """Return the original single-case report and fail on a rejected case."""
    return _audit(forecast_proof, capture_proof, forecast_source_sha=forecast_source_sha,
                  forecast_workflow_sha=forecast_workflow_sha, forecast_run_id=forecast_run_id,
                  forecast_attempt=forecast_attempt, capture_source_sha=capture_source_sha,
                  capture_workflow_sha=capture_workflow_sha, capture_run_id=capture_run_id,
                  capture_attempt=capture_attempt, case_ids=[case_id], paired_sha256=paired_sha256,
                  single=True, now=now)


def audit_cohort(forecast_proof, capture_proof, *, case_ids, **options):
    """Reverify the shared proof once and report each pinned case in request order."""
    return _audit(forecast_proof, capture_proof, case_ids=case_ids, single=False, **options)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-proof', type=Path, required=True)
    parser.add_argument('--capture-proof', type=Path, required=True)
    for prefix in ('forecast', 'capture'):
        for field in ('source-sha', 'workflow-sha', 'run-id', 'attempt'):
            parser.add_argument('--' + prefix + '-' + field, required=True)
    parser.add_argument('--case-id', action='append', required=True,
                        help='Original case ID. Repeat for cases in the same signed archive.')
    parser.add_argument('--paired-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = vars(parser.parse_args(argv))
    output = args.pop('output')
    try:
        for folder in (args['forecast_proof'], args['capture_proof']):
            trusted_result_evidence._output(output, folder)
    except (OSError, ValueError):
        parser.error('output must be a new regular derived file outside both proof directories')
    case_ids = args.pop('case_id')
    report = (audit_case(case_id=case_ids[0], **args) if len(case_ids) == 1
              else audit_cohort(case_ids=case_ids, **args))
    try:
        trusted_result_evidence._write_new(output, report)
    except (OSError, ValueError):
        return 1
    return 0 if report['intake_completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
