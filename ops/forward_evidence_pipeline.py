"""Compose archive binding and evidence rejection; no independent trust decision."""
import json

from ops.forward_admission_preflight import assess, _clock, _text
from ops.forward_forecast_binding import audit_bindings, FIELDS


def audit_pipeline(raw, expected_sha256, claims):
    """Evidence is untrusted; only exact archived identity may enter preflight.

    Recorded kickoff is not actual kickoff. Result identities and clocks are
    merely claims. Even a structurally clean row cannot be certified here.
    """
    if not isinstance(claims, list):
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
                if (not _text(r.get('native_event_id')) or kickoff is None or
                        _clock(r.get('kickoff_utc')) != kickoff or
                        any(r.get(k) != identity[k] for k in ('league', 'home', 'away'))):
                    reasons.append('RESULT_IDENTITY_MISMATCH')
        pending.append((index, row['archive_row_index'], reasons))
    if records:
        checked = assess(raw, records)['rows']
        for (index, archive_row_index, extra), row in zip(pending, checked):
            output['rows'].append(dict(index=index, archive_row_index=archive_row_index,
                                       reasons=list(dict.fromkeys(row['reasons'] + extra))))
    output['rows'].sort(key=lambda r: r['index'])
    return output
