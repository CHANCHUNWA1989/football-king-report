"""Replay one original four-way forecast against controlled result candidates.

The in-process intake performs four fresh CLI checks. They establish controlled
byte provenance, never independent result truth, certified samples or promotion.
No saved intake/replay report or unsigned raw directory is accepted as an input.
Run with PYTHONPATH=ops python -m ops.controlled_case_replay.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from ops import case_fourway_scoring, controlled_case_intake
from ops import trusted_result_evidence


linkage = controlled_case_intake.linkage
capture_provenance = controlled_case_intake.capture_provenance
capture_pack = controlled_case_intake.capture_pack
FORECAST_NAMES = linkage.forecast_provenance_audit.SUBJECT_NAMES
FORECAST_BUNDLE = 'research.sigstore.json'


def _require(condition, reason):
    if not condition:
        raise linkage.LinkageError(reason)


def _snapshot(forecast_proof, capture_proof):
    result = {}
    for folder in (forecast_proof, capture_proof):
        capture_provenance._clean_path(folder)
        _require(folder.is_dir(), 'MISSING_PROOF_DIRECTORY')
    for name in FORECAST_NAMES + (FORECAST_BUNDLE,):
        maximum = (linkage.forecast_provenance_audit.MAX_BUNDLE_BYTES
                   if name == FORECAST_BUNDLE else linkage.forecast_provenance_audit.MAX_FILE_BYTES)
        result[('forecast', name)] = capture_provenance._read(forecast_proof / name, maximum)
    for name, maximum in ((capture_provenance.SUBJECT_NAME, capture_provenance.MAX_TAR_BYTES),
                          (capture_provenance.BUNDLE_NAME, capture_provenance.MAX_BUNDLE_BYTES)):
        result[('capture', name)] = capture_provenance._read(capture_proof / name, maximum)
    return result


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _bind_references(intake, snapshot, options):
    forecast, capture = intake['forecast_reference'], intake['capture_reference']
    for prefix, reference in (('forecast', forecast), ('capture', capture)):
        for key, option in (('source_commit', 'source_sha'), ('workflow_commit', 'workflow_sha'),
                            ('run_id', 'run_id'), ('run_attempt', 'attempt')):
            _require(reference.get(key) == options[prefix + '_' + option],
                     'FRESH_INTAKE_REFERENCE_CONTEXT_MISMATCH')
    expected = {name: _digest(snapshot[('forecast', name)]) for name in FORECAST_NAMES}
    _require(forecast.get('subject_sha256') == expected
             and forecast.get('bundle_sha256') == _digest(snapshot[('forecast', FORECAST_BUNDLE)]),
             'FORECAST_REFERENCE_BYTES_MISMATCH')
    _require(expected['paired.json'] == options['paired_sha256']
             and intake.get('paired_sha256') == options['paired_sha256'],
             'PINNED_PAIRED_DIGEST_MISMATCH')
    _require(capture.get('subject_sha256') == {
        capture_provenance.SUBJECT_NAME: _digest(snapshot[('capture', capture_provenance.SUBJECT_NAME)])}
        and capture.get('bundle_sha256') == _digest(snapshot[('capture', capture_provenance.BUNDLE_NAME)]),
        'CAPTURE_REFERENCE_BYTES_MISMATCH')


def _inputs(intake, snapshot, options):
    paired = linkage._json(snapshot[('forecast', 'paired.json')])
    _require(type(paired) is dict and type(paired.get('comparisons')) is list,
             'INVALID_REPLAY_PAIRED_DOCUMENT')
    selected = [(index, row) for index, row in enumerate(paired['comparisons'])
                if type(row) is dict and row.get('case_id') == options['case_id']]
    _require(len(selected) == 1, 'PINNED_REPLAY_CASE_MISSING_OR_AMBIGUOUS')
    pair_index, pair = selected[0]
    case = intake.get('case')
    _require(type(case) is dict and case.get('case_id') == options['case_id']
             and case.get('pair_index') == pair_index and case.get('fixed_id_linked') is True
             and case.get('ft_candidate') is True, 'NO_LINKED_REGULATION_FINAL_CANDIDATE')
    _require(case.get('paired_sha256') == options['paired_sha256']
             and case.get('forecast_event_id') == pair.get('forecast_event_id')
             and case.get('source_fixture_identity') == pair.get('source_fixture_identity'),
             'REPLAY_CASE_ORIGINAL_FORECAST_MISMATCH')
    members = capture_pack._members(snapshot[('capture', capture_provenance.SUBJECT_NAME)])
    raw_sha, manifest_sha = _digest(members['openligadb.json']), _digest(members['manifest.json'])
    reference = intake['capture_reference']
    _require(raw_sha == intake.get('raw_sha256') == reference.get('raw_sha256') == case.get('raw_sha256')
             and manifest_sha == intake.get('manifest_sha256') == reference.get('manifest_sha256'),
             'REPLAY_RAW_OR_MANIFEST_REFERENCE_MISMATCH')
    rows = linkage._json(members['openligadb.json'])
    index = case.get('raw_index')
    _require(type(rows) is list and type(index) is int and 0 <= index < len(rows),
             'INVALID_REPLAY_RAW_INDEX')
    source = rows[index]
    _require(type(source) is dict and type(source.get('matchID')) is int
             and str(source['matchID']) == case.get('raw_match_id')
             and sum(type(row) is dict and row.get('matchID') == source['matchID'] for row in rows) == 1,
             'REPLAY_RAW_FIXTURE_MISSING_OR_AMBIGUOUS')
    manifest = capture_pack._json(members['manifest.json'])
    capture_time = linkage._utc(manifest.get('captured_utc'), 'INVALID_REPLAY_CAPTURE_TIME')
    candidate = linkage._raw_record(source, index, set(), capture_time)
    _require(candidate.get('ft_candidate') is True
             and candidate.get('score_ft_candidate') == case.get('score_ft_candidate')
             and candidate.get('raw_team_ids') == case.get('raw_team_ids')
             and candidate.get('raw_kickoff_utc') == case.get('raw_kickoff_utc')
             and candidate.get('raw_home') == case.get('raw_home')
             and candidate.get('raw_away') == case.get('raw_away'),
             'REPLAY_FINAL_CANDIDATE_DIFFERENT_FROM_CAPTURE')
    finals = [row for row in source.get('matchResults', [])
              if type(row) is dict and row.get('resultTypeID') == 2]
    _require(len(finals) == 1 and finals[0].get('resultTypeKind') == 'After90Minutes',
             'EXPLICIT_REGULATION_FINAL_CANDIDATE_REQUIRED')
    return pair, candidate['score_ft_candidate']


def _goal_forecast(pair, snapshot):
    """Select rates only from the same original, freshly verified shadow bytes."""
    shadow = linkage._json(snapshot[('forecast', 'shadow.json')])
    _require(type(shadow) is dict and type(shadow.get('predictions')) is list,
             'INVALID_REPLAY_SHADOW_DOCUMENT')
    selected = [(index, forecast) for index, forecast in enumerate(shadow['predictions'])
                if type(forecast) is dict and forecast.get('event_id') == pair['forecast_event_id']]
    _require(len(selected) == 1, 'GOAL_SHADOW_EVENT_MISSING_OR_AMBIGUOUS')
    index, forecast = selected[0]
    _require(forecast.get('prediction_utc') == shadow.get('as_of_utc'),
             'GOAL_SHADOW_DOCUMENT_TIME_MISMATCH')
    return forecast, {'prediction_index': index,
                      'sha256': _digest(snapshot[('forecast', 'shadow.json')])}


def audit_replay(forecast_proof, capture_proof, *, forecast_source_sha, forecast_workflow_sha,
                 forecast_run_id, forecast_attempt, capture_source_sha, capture_workflow_sha,
                 capture_run_id, capture_attempt, case_id, paired_sha256, now=None):
    report = {**linkage._safety(), 'schema': 'football-king-controlled-case-replay-v1',
              'replay_completed': False, 'candidate_score_replay_completed': False,
              'candidate_only': True, 'derived_review_not_a_trust_input': True,
              'certified_case_count': 0, 'scoring': None, 'models': None, 'case': None,
              'goal_market_scoring': None, 'goal_market_replay_completed': False,
              'goal_market_reason': 'REPLAY_NOT_COMPLETED', 'goal_market_shadow_reference': None,
              'intake': None, 'blockers': list(controlled_case_intake.BLOCKERS),
              'notice': '受控原件與原封存四方評分重播；未認證賽果，不能計入正式資格。'}
    options = dict(forecast_source_sha=forecast_source_sha, forecast_workflow_sha=forecast_workflow_sha,
                   forecast_run_id=forecast_run_id, forecast_attempt=forecast_attempt,
                   capture_source_sha=capture_source_sha, capture_workflow_sha=capture_workflow_sha,
                   capture_run_id=capture_run_id, capture_attempt=capture_attempt,
                   case_id=case_id, paired_sha256=paired_sha256)
    try:
        current = datetime.now(timezone.utc) if now is None else now
        _require(isinstance(current, datetime) and current.tzinfo is not None, 'INVALID_REPLAY_CLOCK')
        current = current.astimezone(timezone.utc)
        before = _snapshot(forecast_proof, capture_proof)
        intake = controlled_case_intake.audit_case(forecast_proof, capture_proof, **options, now=current)
        report['intake'] = intake
        _require(intake.get('intake_completed') is True
                 and intake.get('controlled_capture_signature_reverified') is True
                 and intake.get('forecast_signature_reverified') is True
                 and intake.get('controlled_capture_to_forecast_link_verified') is True,
                 'FRESH_CONTROLLED_INTAKE_FAILED')
        report['blockers'] = list(intake['blockers'])
        _require(_snapshot(forecast_proof, capture_proof) == before,
                 'PROOF_BYTES_CHANGED_DURING_CASE_REPLAY')
        _bind_references(intake, before, options)
        # Read the paired document through the strict duplicate/nonfinite JSON
        # boundary after intake, and bind it to the actually verified subject.
        paired = linkage._read(forecast_proof / 'paired.json',
                               linkage.forecast_provenance_audit.MAX_FILE_BYTES)
        _require(paired == before[('forecast', 'paired.json')] and _digest(paired) == paired_sha256,
                 'PINNED_PAIRED_CHANGED_AFTER_FRESH_INTAKE')
        pair, score_ft = _inputs(intake, before, options)
        try:
            scoring = case_fourway_scoring.score_case(pair, score_ft)
        except ValueError as exc:
            raise linkage.LinkageError('FOUR_WAY_SCORE_INPUT_REJECTED') from exc
        forecast, goal_reference = _goal_forecast(pair, before)
        goal_scoring = None
        goal_reason = 'SEALED_GOAL_RATES_MISSING'
        # Legacy seals stay unchanged and can still produce the original 1X2
        # replay. Never infer absent goal rates from their three probabilities.
        if any(key in forecast for key in ('expected_home_goals', 'expected_away_goals')):
            from ops import case_goal_market_scoring
            try:
                goal_scoring = case_goal_market_scoring.score_goal_markets(pair, forecast, score_ft)
            except ValueError as exc:
                raise linkage.LinkageError('GOAL_MARKET_SCORE_INPUT_REJECTED') from exc
            goal_reason = 'SEALED_A_RATE_DERIVED_GOAL_MARKET_REPLAY_COMPLETED'
        _require(_snapshot(forecast_proof, capture_proof) == before,
                 'PROOF_BYTES_CHANGED_DURING_CASE_REPLAY')
        report.update(
            replay_completed=True, candidate_score_replay_completed=True,
            checked_utc=current.isoformat(), case_id=case_id, paired_sha256=paired_sha256,
            raw_sha256=intake['raw_sha256'], manifest_sha256=intake['manifest_sha256'],
            scoring=scoring, models=scoring['models'], case=intake['case'],
            goal_market_scoring=goal_scoring, goal_market_replay_completed=goal_scoring is not None,
            goal_market_reason=goal_reason,
            goal_market_shadow_reference=goal_reference if goal_scoring is not None else None,
            forecast_reference=intake['forecast_reference'], capture_reference=intake['capture_reference'],
            source_policy=intake['source_policy'],
            recorded_prediction_utc=pair['prediction_utc'],
            recorded_market_snapshot_utc=pair['market_snapshot_utc'],
            recorded_market_updated_utc=pair['market_updated_utc'],
            recorded_kickoff_utc=pair['kickoff_utc'],
            claimed_raw_capture_utc=intake['claimed_raw_capture_utc'],
            claimed_source_response_completed_utc=intake['claimed_source_response_completed_utc'],
            reason='CONTROLLED_CANDIDATE_FOUR_WAY_SCORE_REPLAY_COMPLETED')
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        report.update(replay_completed=False, candidate_score_replay_completed=False,
                      scoring=None, models=None, case=None,
                      goal_market_scoring=None, goal_market_replay_completed=False,
                      goal_market_shadow_reference=None, goal_market_reason='REPLAY_NOT_COMPLETED',
                      reason=str(exc) if isinstance(exc, linkage.LinkageError)
                      else 'CONTROLLED_CASE_REPLAY_INPUT_OR_PROOF_REJECTED')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast-proof', type=Path, required=True)
    parser.add_argument('--capture-proof', type=Path, required=True)
    for prefix in ('forecast', 'capture'):
        for field in ('source-sha', 'workflow-sha', 'run-id', 'attempt'):
            parser.add_argument('--' + prefix + '-' + field, required=True)
    parser.add_argument('--case-id', required=True)
    parser.add_argument('--paired-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = vars(parser.parse_args(argv))
    output = args.pop('output')
    try:
        for folder in (args['forecast_proof'], args['capture_proof']):
            trusted_result_evidence._output(output, folder)
    except (OSError, ValueError):
        parser.error('output must be a new regular derived file outside both proof directories')
    result = audit_replay(**args)
    try:
        trusted_result_evidence._write_new(output, result)
    except (OSError, ValueError):
        return 1
    return 0 if result['replay_completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
