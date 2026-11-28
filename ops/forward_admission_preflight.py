"""Offline rejection diagnostics only. No authentication or production admission."""
import hashlib
from collections import Counter
from datetime import datetime, timedelta


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _clock(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt if dt.utcoffset() == timedelta(0) else None
    except (ValueError, OverflowError):
        return None


def _score(value):
    return (isinstance(value, list) and len(value) == 2 and
            all(type(x) is int and 0 <= x <= 99 for x in value))


def assess(forecast_bytes, records):
    """Check untrusted claims; even a clean row requires independent verification.

    The hash only binds supplied bytes, not a row to its fixture or source.
    Kickoff, witness, publisher and upstream labels are claims, not proofs.
    The 120-minute floor is necessary, never sufficient for actual completion.
    This module deliberately has no certification or promotion path.
    """
    if type(forecast_bytes) is not bytes or not isinstance(records, list):
        raise ValueError('expected bytes and list')
    digest = hashlib.sha256(forecast_bytes).hexdigest()
    counts = Counter(r['fixture_key'] for r in records if isinstance(r, dict)
                     and _text(r.get('fixture_key')))
    rows = []
    for index, r in enumerate(records):
        if not isinstance(r, dict):
            rows.append(dict(index=index, reasons=['INVALID_ROW']))
            continue
        reasons = []
        key = r.get('fixture_key')
        if not forecast_bytes or r.get('forecast_sha256') != digest:
            reasons.append('HASH_MISMATCH')
        if not all(_text(r.get(k)) for k in ('fixture_key', 'league', 'native_event_id')):
            reasons.append('IDENTITY_UNVERIFIED')
        if _text(key) and counts[key] > 1:
            reasons.append('DUPLICATE_FIXTURE')
        kickoff, witness = _clock(r.get('kickoff_utc')), _clock(r.get('witness_utc'))
        if kickoff is None:
            reasons.append('KICKOFF_UNVERIFIED')
        if witness is None or kickoff is None or witness >= kickoff:
            reasons.append('FORECAST_NOT_PRE_KICKOFF')
        results = r.get('results')
        if not isinstance(results, list) or len(results) != 2 or not all(isinstance(x, dict) for x in results):
            reasons.append('SOURCE_INDEPENDENCE_UNVERIFIED')
        else:
            for field in ('publisher', 'upstream'):
                vals = [x.get(field) for x in results]
                if not all(_text(v) for v in vals) or len({v.casefold() for v in vals}) != 2:
                    reasons.append('SOURCE_INDEPENDENCE_UNVERIFIED')
            clocks = [_clock(x.get('collection_start_utc')) for x in results]
            if kickoff is None or any(c is None or c - kickoff < timedelta(hours=2) for c in clocks):
                reasons.append('RESULT_NOT_POST_MATCH')
            if any(x.get('final') is not True or not _score(x.get('score')) for x in results):
                reasons.append('RESULT_NOT_FINAL')
            elif results[0]['score'] != results[1]['score']:
                reasons.append('SCORE_CONFLICT')
        reasons.append('INDEPENDENT_VERIFICATION_REQUIRED')
        rows.append(dict(index=index, reasons=list(dict.fromkeys(reasons))))
    return dict(status='HOLD', production_recommendations='DISABLED',
                authenticated_samples=0, formal_metrics=None, candidate_count=len(records), rows=rows)
