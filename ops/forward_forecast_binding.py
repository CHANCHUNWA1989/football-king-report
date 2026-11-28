"""Research-only binding to archived bytes, never independent certification."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta

FIELDS = ('league', 'event_id', 'home', 'away', 'kickoff_utc', 'prediction_utc')
MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 10000


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError('nonfinite JSON constant')


def _clock(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt if dt.utcoffset() == timedelta(0) else None
    except (ValueError, OverflowError, AttributeError):
        return None


def _key(row):
    if not isinstance(row, dict):
        return None
    values = tuple(row.get(k) for k in FIELDS)
    if not all(isinstance(v, str) and v and v.strip() == v for v in values):
        return None
    kickoff, prediction = map(_clock, values[-2:])
    if kickoff is None or prediction is None or prediction >= kickoff or values[2] == values[3]:
        return None
    return values


def audit_bindings(raw, expected_sha256, claims):
    """Compare identity/time fields to exact rows in externally pinned bytes.

    Expected digest is supplied by the caller; this is not a trust decision.
    Recorded kickoff and prediction clocks are not independently authenticated.
    Claims cannot supply an alternate row, and no result can certify a sample.
    """
    if not isinstance(claims, list) or len(claims) > MAX_ROWS:
        raise ValueError('claims must be a bounded list')
    result = dict(status='HOLD', production_recommendations='DISABLED',
                  authenticated_samples=0, formal_metrics=None, bound_count=0,
                  candidate_count=len(claims), rows=[])

    def reject(reason):
        result['archive_reason'] = reason
        result['rows'] = [dict(index=i, reason=reason) for i in range(len(claims))]
        return result

    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        return reject('INVALID_ARCHIVE')
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        return reject('ARCHIVE_DIGEST_MISMATCH')
    try:
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique, parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError):
        return reject('INVALID_ARCHIVE')
    if not isinstance(doc, dict):
        return reject('INVALID_ARCHIVE')
    rows = doc.get('predictions')
    count = doc.get('predictions_count')
    if not isinstance(rows, list) or len(rows) > MAX_ROWS or type(count) is not int or count != len(rows):
        return reject('INVALID_ARCHIVE')
    keys = [_key(row) for row in rows]
    if any(k is None for k in keys):
        return reject('INVALID_ARCHIVE_ROW')
    events = [(k[0], k[1]) for k in keys]
    fixtures = [(k[0], k[2], k[3], _clock(k[4])) for k in keys]
    if len(set(events)) != len(keys) or len(set(fixtures)) != len(keys):
        return reject('AMBIGUOUS_ARCHIVE_IDENTITY')
    index = {key: i for i, key in enumerate(keys)}
    requested = [_key(claim) for claim in claims]
    counts = Counter(k for k in requested if k is not None)
    result['archive_reason'] = 'ARCHIVE_BYTES_MATCH'
    result['archive_sha256'] = digest
    for i, key in enumerate(requested):
        if key is None:
            reason = 'INVALID_CLAIM'
        elif counts[key] != 1:
            reason = 'DUPLICATE_CLAIM'
        elif key not in index:
            reason = 'NO_EXACT_ARCHIVED_ROW'
        else:
            result['bound_count'] += 1
            result['rows'].append(dict(index=i, reason='EXACT_ARCHIVED_ROW', archive_row_index=index[key]))
            continue
        result['rows'].append(dict(index=i, reason=reason))
    return result
