"""Offline, research-only comparison of point-in-time 1X2 vectors."""
from datetime import datetime, timezone
from math import isfinite


def _utc(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError('INVALID_TIME')
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError('NAIVE_TIME')
    return t.astimezone(timezone.utc)


def _id(value):
    if not isinstance(value, str) or not 0 < len(value) <= 512 or value.strip() != value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('INVALID_ID')
    return value


def _vector(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3 or any(type(x) not in (int, float) or not 0 <= x <= 1 or not isfinite(x) for x in value):
        raise ValueError('INVALID_VECTOR')
    total = sum(value)
    if abs(total - 1) > 0.0001:
        raise ValueError('INVALID_VECTOR_SUM')
    return tuple(x / total for x in value)


def audit(left, right, *, as_of_utc):
    """Exact caller-provided fixture binding; does not authenticate providers."""
    out = {'status': 'HOLD', 'reason': 'INVALID_INPUT', 'max_gap': None,
           'direction_disagreement': None, 'source_authenticated': False,
           'model_calibrated': False, 'production_recommendations': 'DISABLED',
           'can_recommend_bets': False}
    try:
        now = _utc(as_of_utc)
        rows = []
        for r in (left, right):
            if not isinstance(r, dict):
                raise ValueError('INVALID_ROW')
            fixture = tuple(_id(r[k]) for k in ('event_id', 'league', 'home_id', 'away_id'))
            if fixture[2] == fixture[3]:
                raise ValueError('SELF_MATCH')
            model = _id(r['model_id'])
            ko, cutoff, generated = (_utc(r[k]) for k in ('kickoff_utc', 'information_cutoff_utc', 'prediction_utc'))
            if not cutoff <= generated <= now < ko:
                raise ValueError('INVALID_CHRONOLOGY')
            if (now - cutoff).total_seconds() > 10 * 3600:
                raise ValueError('STALE_INPUT')
            rows.append((fixture, model, ko, cutoff, _vector(r['p'])))
        a, b = rows
        if a[0] != b[0] or a[2] != b[2]:
            raise ValueError('FIXTURE_MISMATCH')
        if a[1] == b[1]:
            raise ValueError('DUPLICATE_MODEL')
        if a[3] != b[3]:
            raise ValueError('CUTOFF_MISMATCH')
    except (ValueError, TypeError, KeyError, OverflowError):
        return out
    pa, pb = a[4], b[4]
    gap = max(abs(x-y) for x,y in zip(pa,pb))
    def leaders(p):
        return {i for i,v in enumerate(p) if max(p)-v <= 1e-12}
    disagreement = leaders(pa) != leaders(pb)
    # Diagnostic thresholds, not fitted or promoted parameters.
    reason = 'DIRECTION_CONFLICT' if disagreement else 'LARGE_GAP' if gap >= 0.10 - 1e-12 else 'NO_LARGE_DISAGREEMENT'
    return {**out, 'reason': reason, 'max_gap': gap,
            'direction_disagreement': disagreement,
            'status': 'HOLD' if disagreement or gap >= 0.10 - 1e-12 else 'RESEARCH_ONLY'}
