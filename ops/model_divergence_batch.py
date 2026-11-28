"""Bounded, offline batch adapter. No automatic model promotion or source trust."""
from collections import Counter
from ops.model_divergence_guard import audit, _id, _utc

MAX_FIXTURES = 3000


def evaluate(expected_ids, left_rows, right_rows, *, as_of_utc):
    """Require explicit coverage; never infer missing clocks or join by names.

    Results use manifest positions, not untrusted source strings. A malformed
    manifest or duplicate/out-of-scope source row invalidates the entire batch.
    """
    base = dict(schema='football-king-model-divergence-batch-v1', status='HOLD',
                reason='INVALID_BATCH', results=[], counts={},
                source_authenticated=False, model_calibrated=False,
                production_recommendations='DISABLED', can_recommend_bets=False)
    try:
        _utc(as_of_utc)
        if not isinstance(expected_ids, list) or not 1 <= len(expected_ids) <= MAX_FIXTURES:
            raise ValueError('INVALID_MANIFEST')
        ids = [_id(x) for x in expected_ids]
        allowed = set(ids)
        if len(allowed) != len(ids):
            raise ValueError('DUPLICATE_MANIFEST_ID')
        indexes = []
        for source in (left_rows, right_rows):
            if not isinstance(source, list) or len(source) > MAX_FIXTURES:
                raise ValueError('INVALID_SOURCE')
            index = {}
            for row in source:
                if not isinstance(row, dict):
                    raise ValueError('INVALID_ROW')
                event = _id(row['event_id'])
                if event not in allowed or event in index:
                    raise ValueError('DUPLICATE_OR_OUT_OF_SCOPE')
                index[event] = row
            indexes.append(index)
    except (ValueError, TypeError, KeyError, OverflowError):
        return base
    results = []
    for i, event in enumerate(ids):
        a, b = (x.get(event) for x in indexes)
        if a is None or b is None:
            result = dict(status='HOLD', reason='MISSING_PAIR', max_gap=None)
        else:
            result = audit(a, b, as_of_utc=as_of_utc)
        results.append(dict(manifest_index=i, status=result['status'],
                            reason=result['reason'], max_gap=result['max_gap']))
    counts = dict(Counter(r['reason'] for r in results))
    all_clear = all(r['status'] == 'RESEARCH_ONLY' for r in results)
    return {**base, 'status': 'RESEARCH_ONLY' if all_clear else 'HOLD',
            'reason': 'COMPLETE_RESEARCH_COMPARISON' if all_clear else 'PAIR_HOLD',
            'results': results, 'counts': counts}
