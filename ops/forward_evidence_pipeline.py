"""Compose archive binding and evidence rejection; no independent trust decision."""
import json
from collections import defaultdict

from ops.forward_admission_preflight import assess, _clock, _text
from ops.forward_forecast_binding import audit_bindings, FIELDS, MAX_ROWS


def audit_pipeline(raw, expected_sha256, claims):
    """Evidence is untrusted; only exact archived identity may enter preflight.

    Recorded kickoff is not actual kickoff. Result identities and clocks are
    merely claims. Even a structurally clean row cannot be certified here.
    """
    if not isinstance(claims, list) or len(claims) > MAX_ROWS:
        raise ValueError('claims must be a bounded list')
    identities = [c.get('identity') if isinstance(c, dict) else None for c in claims]
    binding = audit_bindings(raw, expected_sha256, identities)
    output = dict(status='HOLD', production_recommendations='DISABLED',
                  authenticated_samples=0, formal_metrics=None,
                  candidate_count=binding['candidate_count'], bound_count=binding['bound_count'],
                  archive_reason=binding['archive_reason'], rows=[])
    if 'archive_sha256' in binding:
        output['archive_sha256'] = binding['archive_sha256']
    records, pending = [], []
    source_ids = defaultdict(set)
    claim_ids = defaultdict(set)
    for row in binding['rows']:
        index = row['index']
        if row['reason'] != 'EXACT_ARCHIVED_ROW':
            output['rows'].append(dict(index=index, reasons=[row['reason']]))
            continue
        identity = identities[index]
        evidence = claims[index].get('evidence')
        if not isinstance(evidence, dict):
            evidence = {}
        kickoff = _clock(evidence.get('actual_kickoff_utc'))
        witness = _clock(evidence.get('witness_utc'))
        prediction, recorded = _clock(identity['prediction_utc']), _clock(identity['kickoff_utc'])
        results = evidence.get('results')
        record = dict(fixture_key=json.dumps([identity[k] for k in FIELDS], ensure_ascii=True),
                      forecast_sha256=binding['archive_sha256'], league=identity['league'],
                      native_event_id=evidence.get('native_event_id'),
                      kickoff_utc=evidence.get('actual_kickoff_utc'),
                      witness_utc=evidence.get('witness_utc'), results=results)
        # Never accept approval flags or identity substitutions from evidence.
        reasons = []
        records.append(record)
        if witness is None or not prediction <= witness < recorded:
            reasons.append('WITNESS_OUTSIDE_ARCHIVED_WINDOW')
        if kickoff is not None and prediction >= kickoff:
            reasons.append('PREDICTION_NOT_PRE_ACTUAL_KICKOFF')
        if isinstance(results, list) and len(results) == 2 and all(isinstance(r, dict) for r in results):
            for r in results:
                # Only compare claimed identifiers in the same publisher/upstream
                # namespace. Reuse across distinct archived rows is a conflict,
                # not proof of identity even when no conflict is found.
                native = r.get('native_event_id')
                if _text(native):
                    for namespace in ('publisher', 'upstream'):
                        label = r.get(namespace)
                        if _text(label):
                            source_ids[(namespace, label.casefold(), native)].add(index)
                if (not _text(r.get('native_event_id')) or kickoff is None or
                        _clock(r.get('kickoff_utc')) != kickoff or
                        any(r.get(k) != identity[k] for k in ('league', 'home', 'away'))):
                    reasons.append('RESULT_IDENTITY_MISMATCH')
        pending.append((index, row['archive_row_index'], reasons))
    for indexes in source_ids.values():
        if len(indexes) > 1:
            for index in indexes:
                claim_ids[index].add('RESULT_NATIVE_ID_REUSED_ACROSS_FIXTURES')
    if records:
        checked = assess(raw, records)['rows']
        for (index, archive_row_index, extra), row in zip(pending, checked):
            output['rows'].append(dict(index=index, archive_row_index=archive_row_index,
                                       reasons=list(dict.fromkeys(row['reasons'] + extra + sorted(claim_ids[index])))))
    output['rows'].sort(key=lambda r: r['index'])
    return output


MAX_BATCHES = 32
MAX_BATCH_BYTES = 64 * 1024 * 1024


def audit_batches(batches):
    """Bounded offline diagnostics across separately pinned forecast archives.

    Repeated exact fixture keys are repeated observations, not extra samples.
    All identifiers and clocks remain claims; no certification or persistence.
    """
    if not isinstance(batches, list) or len(batches) > MAX_BATCHES:
        raise ValueError('invalid batch count')
    total_bytes = total_claims = 0
    for batch in batches:
        if (not isinstance(batch, dict) or set(batch) != {'raw', 'expected_sha256', 'claims'}
                or type(batch['raw']) is not bytes or not isinstance(batch['claims'], list)):
            raise ValueError('invalid batch input')
        total_bytes += len(batch['raw'])
        total_claims += len(batch['claims'])
        if total_bytes > MAX_BATCH_BYTES or total_claims > MAX_ROWS:
            raise ValueError('aggregate batch budget exceeded')
    reports = []
    fixtures = defaultdict(list)
    events = defaultdict(set)
    native = defaultdict(set)
    for bidx, batch in enumerate(batches):
        report = audit_pipeline(batch['raw'], batch['expected_sha256'], batch['claims'])
        reports.append(report)
        for row in report['rows']:
            if 'archive_row_index' not in row:
                continue
            claim = batch['claims'][row['index']]
            ident = claim['identity']
            key = (ident['league'], ident['home'], ident['away'], _clock(ident['kickoff_utc']))
            fixtures[key].append((bidx, row, ident['event_id']))
            events[(ident['league'], ident['event_id'])].add(key)
            evidence = claim.get('evidence')
            results = evidence.get('results') if isinstance(evidence, dict) else None
            if isinstance(results, list) and len(results) == 2 and all(isinstance(r, dict) for r in results):
                for r in results:
                    if not _text(r.get('native_event_id')):
                        continue
                    for namespace in ('publisher', 'upstream'):
                        label = r.get(namespace)
                        if _text(label):
                            native[(namespace, label.casefold(), r['native_event_id'])].add(key)
    conflicts = defaultdict(set)
    for keys in events.values():
        if len(keys) > 1:
            for key in keys:
                conflicts[key].add('ARCHIVED_EVENT_ID_MULTIPLE_FIXTURES')
    for keys in native.values():
        if len(keys) > 1:
            for key in keys:
                conflicts[key].add('RESULT_NATIVE_ID_MULTIPLE_FIXTURES')
    repeated = 0
    for key, observations in fixtures.items():
        if len({event for _, _, event in observations}) > 1:
            conflicts[key].add('ARCHIVED_FIXTURE_MULTIPLE_EVENT_IDS')
        if len(observations) > 1:
            repeated += len(observations) - 1
        for _, row, _ in observations:
            flags = set(conflicts[key])
            if len(observations) > 1:
                flags.add('REPEATED_FIXTURE_OBSERVATION')
            row['cross_archive_reasons'] = sorted(flags)
    return dict(status='HOLD', production_recommendations='DISABLED',
                authenticated_samples=0, formal_metrics=None,
                batch_count=len(batches), candidate_count=total_claims,
                bound_observation_count=sum(len(v) for v in fixtures.values()),
                distinct_exact_fixture_count=len(fixtures),
                repeated_observation_count=repeated,
                conflicting_fixture_count=sum(bool(v) for v in conflicts.values()),
                reports=reports)
