"""Audit signed result observations against a pinned, restrictive source policy.

Fresh cryptographic capture verification and replay can establish which bytes a
controlled job observed. They cannot establish publisher truth, independent
collection, cross-publisher identity, actual kickoff or a certified final score.
This first policy explicitly records those missing facts; it has no promotion
path and never feeds observations into the settled scoring ledger.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

from ops import ndr_capture_provenance as capture_provenance
from ops.ndr_capture_pack import _json, _members, _same, validate_capture
from ops.ndr_result_observations import parse_html


POLICY_FILE = Path(__file__).with_name('policies') / 'result_sources_v1.json'
POLICY_SHA256 = '33abd884142cc8000844d82cf9886446e4fe27a823f95577d06e4f8d232c6463'
PROVIDERS = frozenset(('NDR', 'DFB', 'OpenLigaDB', 'OpenFootball'))
BLOCKERS = (
    'INDEX_ORIGIN_CHAIN_INCOMPLETE',
    'CROSS_SOURCE_FIXTURE_MAPPING_MISSING',
    'ACTUAL_KICKOFF_EVIDENCE_MISSING',
    'REGULATION_RESULT_NOT_INDEPENDENTLY_AUTHENTICATED',
    'INDEPENDENT_UPSTREAM_COLLECTION_EVIDENCE_MISSING',
    'INDEPENDENT_RESULT_SOURCE_MISSING',
    'AUTHENTICATED_PREMATCH_FORECAST_LINK_MISSING',
)


def _require(condition, reason):
    if not condition:
        raise capture_provenance.AuditError(reason)


def _policy():
    raw = capture_provenance._read(POLICY_FILE, 32_000)
    _require(hashlib.sha256(raw).hexdigest() == POLICY_SHA256, 'SOURCE_POLICY_DIGEST_MISMATCH')
    value = _json(raw)
    _require(set(value) == {'schema', 'policy_id', 'scope', 'providers', 'notice'}
             and value['schema'] == 'football-king-result-source-policy-v1'
             and value['policy_id'] == 'result-sources-20261019-v1'
             and value['scope'] == 'bundesliga/2026-2027/regulation-90-minutes'
             and isinstance(value['providers'], dict)
             and set(value['providers']) == PROVIDERS, 'INVALID_SOURCE_POLICY')
    for item in value['providers'].values():
        _require(isinstance(item, dict) and set(item) == {
            'publisher', 'upstream_relationship', 'independent_result_collection_evidence',
            'public_raw_reuse', 'discovery_clues', 'clue_scope'}
            and item['upstream_relationship'] == 'UNKNOWN'
            and item['independent_result_collection_evidence'] == []
            and isinstance(item['discovery_clues'], list)
            and all(isinstance(url, str) and url.startswith('https://') for url in item['discovery_clues'])
            and all(isinstance(item[key], str) and item[key] for key in (
                'publisher', 'public_raw_reuse', 'clue_scope')), 'INVALID_SOURCE_POLICY')
    return value


def _blockers(origin_complete):
    return ([reason for reason in BLOCKERS if reason != 'INDEX_ORIGIN_CHAIN_INCOMPLETE']
            + ['PUBLISHER_IDENTITY_NOT_INDEPENDENTLY_AUTHENTICATED']) if origin_complete else list(BLOCKERS)


def _case(observation, capture, policy, origin_complete, receipt):
    source = observation['detail_source']
    return {
        'provider': 'NDR',
        'provider_fixture_id': observation['provider_fixture_id'],
        'home_provider_team_id': observation['home_provider_team_id'],
        'away_provider_team_id': observation['away_provider_team_id'],
        'fixture_url': observation['fixture_url'],
        'season': observation['season'], 'date_local': observation['date_local'],
        'league': 'bundesliga', 'display_score': observation['display_score'],
        'completion_display': observation['completion_display'],
        'end_event_display': observation['end_event_display'],
        'end_event_clock': observation['end_event_clock'],
        'controlled_capture_status': 'VERIFIED',
        'provider_local_identity_status': 'PROVIDER_LOCAL_DISPLAY_MATCHED',
        'index_origin_chain_status': ('CONTROLLED_ENDPOINT_CAPTURE_REPLAYED' if origin_complete
                                      else 'INCOMPLETE_FINAL_URL_NOT_RECORDED'),
        'index_origin_chain_scope': 'NDR_INDEX_ONLY',
        'index_endpoint_receipt': receipt,
        'detail_endpoint_metadata_status': 'EXACT_RECORDED_FINAL_URL_NO_REDIRECT',
        'publisher_identity_status': 'UNAUTHENTICATED',
        'cross_source_fixture_mapping_status': 'UNKNOWN',
        'scheduled_kickoff_utc': None,
        'scheduled_kickoff_status': 'NOT_AUTHENTICATED',
        'actual_kickoff_utc': None, 'actual_kickoff_status': 'UNKNOWN',
        'forecast_link_status': 'NOT_LINKED',
        'completion_display_observed': True,
        'regulation_result_status': 'UNVERIFIED',
        'upstream_independence_status': policy['providers']['NDR']['upstream_relationship'],
        'source_policy_id': policy['policy_id'],
        'raw_member': source['raw_file'], 'raw_sha256': source['raw_sha256'],
        'recorded_requested_utc': source['requested_utc'],
        'recorded_captured_utc': source['captured_utc'],
        'verified_tlog_utc': capture['verified_tlog_utc'],
        'independently_verified': False, 'eligible_for_model_scoring': False,
        'eligible_for_betting_promotion': False,
        'status': 'HOLD', 'production_recommendations': 'DISABLED',
        'blockers': _blockers(origin_complete),
    }


def audit(proof: Path, *, source_sha, workflow_sha, run_id, attempt, now=None):
    report = {
        'schema': 'football-king-trusted-result-evidence-v1',
        'status': 'HOLD', 'production_recommendations': 'DISABLED',
        'audit_completed': False, 'independently_verified_count': 0,
        'independently_verified': False, 'outcomes_independently_authenticated': False,
        'eligible_for_model_scoring': False, 'eligible_for_betting_promotion': False,
        'cases': [], 'coverage': {},
        'notice': '逐場核對受控原件及來源政策；缺獨立上游、身份或實際開波證據維持HOLD。',
    }
    # No saved verification JSON or caller-selected policy is an input.
    capture = capture_provenance.audit(proof, source_sha=source_sha, workflow_sha=workflow_sha,
                                       run_id=run_id, attempt=attempt, now=now)
    report['capture_audit'] = capture
    try:
        _require(isinstance(capture, dict) and all(capture.get(key) is True for key in (
            'audit_completed', 'signature_identity_and_subject_verified', 'capture_content_replayed')),
            'CAPTURE_VERIFICATION_FAILED')
        raw = capture_provenance._read(proof / capture_provenance.SUBJECT_NAME,
                                       capture_provenance.MAX_TAR_BYTES)
        bundle = capture_provenance._read(proof / capture_provenance.BUNDLE_NAME,
                                          capture_provenance.MAX_BUNDLE_BYTES)
        _require(capture.get('subject_sha256') == {
            capture_provenance.SUBJECT_NAME: hashlib.sha256(raw).hexdigest()},
            'CAPTURE_BYTES_CHANGED_AFTER_VERIFICATION')
        _require(capture.get('bundle_sha256') == hashlib.sha256(bundle).hexdigest(),
                 'BUNDLE_BYTES_CHANGED_AFTER_VERIFICATION')
        current = datetime.now(timezone.utc) if now is None else now
        witness = capture_provenance._time(capture.get('verified_tlog_utc'))
        try:
            replay = validate_capture(raw, witness=witness, now=current)
            _same(capture.get('capture_summary'), replay, 'CAPTURE_SUMMARY_CHANGED')
            files = _members(raw)  # Same strict canonical, bounded tar reader.
            stored = _json(files['report.json'])
            rows, _ = parse_html(files['ndr.html']) if 'ndr.html' in files else ([], [])
        except (ValueError, KeyError) as exc:
            raise capture_provenance.AuditError('CAPTURE_CONTENT_REPLAY_FAILED') from exc
        policy = _policy()
        origin_complete = replay['index_origin_chain_complete'] is True
        index_manifest = _json(files['index-manifest.json'])
        receipt = (next(source for source in index_manifest['sources'] if source['provider'] == 'NDR')
                   if origin_complete else None)
        cases = [_case(item, capture, policy, origin_complete, receipt) for item in stored['observations']]
        accepted = [row['provider_fixture_id'] for row in rows]
        attempted = [row['provider_fixture_id'] for row in stored['sources']]
        observed = [row['provider_fixture_id'] for row in cases]
        report.update(
            audit_completed=True, checked_utc=current.isoformat(), cases=cases,
            source_policy={'id': policy['policy_id'], 'sha256': POLICY_SHA256, 'scope': policy['scope'],
                           'upstream_relationships': {name: item['upstream_relationship']
                                                     for name, item in policy['providers'].items()},
                           'discovery_clues_are_not_authenticated_source_evidence': True},
            coverage={'accepted_index_fixture_ids': accepted, 'attempted_detail_fixture_ids': attempted,
                      'observed_fixture_ids': observed,
                      'uncovered_fixture_ids': [item for item in accepted if item not in observed]},
            fetch_errors=stored['fetch_errors'], display_rejections=stored['rejections'],
            index_rejected_row_count=replay['index_rejected_row_count'],
            selection_policy='FIRST_THREE_ACCEPTED_INDEX_ROWS_NO_ROTATION_YET',
            index_origin_schema=replay['index_origin_schema'],
            index_origin_chain_complete=origin_complete, index_origin_chain_scope='NDR_INDEX_ONLY',
            blockers=_blockers(origin_complete),
            reason='CAPTURE_REPLAYED_RESULT_AUTHENTICATION_INCOMPLETE')
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        report['reason'] = (str(exc) if isinstance(exc, capture_provenance.AuditError)
                            else 'RESULT_EVIDENCE_INPUT_OR_POLICY_ERROR')
    return report


def _output(path, proof):
    capture_provenance._clean_path(path)
    _require(path.parent.is_dir() and not path.resolve().is_relative_to(proof.resolve()) and not path.exists(),
             'UNSAFE_DERIVED_OUTPUT')
    _require(path.resolve() != POLICY_FILE.resolve(), 'UNSAFE_DERIVED_OUTPUT')


def _write_new(path, report):
    capture_provenance._clean_path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags, 0o600), 'w') as stream:
        info = os.fstat(stream.fileno())
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'UNSAFE_DERIVED_OUTPUT')
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof', type=Path, required=True)
    for name in ('source-sha', 'workflow-sha', 'run-id', 'attempt'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--capture-audit-output', type=Path)
    args = parser.parse_args(argv)
    outputs = [path for path in (args.output, args.capture_audit_output) if path is not None]
    try:
        capture_provenance._clean_path(args.proof)
        for path in outputs:
            _output(path, args.proof)
        _require(len({path.resolve() for path in outputs}) == len(outputs), 'ALIASED_DERIVED_OUTPUTS')
    except (OSError, ValueError):
        parser.error('outputs must be distinct new regular derived files outside proof')
    result = audit(args.proof, source_sha=args.source_sha, workflow_sha=args.workflow_sha,
                   run_id=args.run_id, attempt=args.attempt)
    try:
        _write_new(args.output, result)
        if args.capture_audit_output is not None:
            _write_new(args.capture_audit_output, result['capture_audit'])
    except (OSError, ValueError):
        return 1
    return 0 if result['audit_completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
