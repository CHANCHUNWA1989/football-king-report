"""Replay a bounded UTC-day NDR selection without authenticating any fixture.

For a stable cohort and constant limit, one completed run per consecutive UTC
day schedules every ID within ceil(cohort size / limit) days. Retries within one
day repeat that day's batch. Changed cohorts, missed days and unsuccessful GETs
do not acquire a coverage guarantee or an independent-results claim.
"""
from datetime import datetime, timezone
import hashlib
import json
import re


POLICY = 'UTC_DAY_CYCLIC_NUMERIC_FIXTURE_IDS_V1'
ORDER = 'NUMERIC_PROVIDER_FIXTURE_ID_ASCENDING'
MAX_REQUESTS = 3
MAX_COHORT = 10_000
PROVIDER_ID = re.compile(r'[1-9][0-9]{0,9}\Z')
UTC_TIME = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)\Z')


def _utc(value):
    if isinstance(value, str):
        if not UTC_TIME.fullmatch(value):
            raise ValueError('INVALID_NDR_SELECTION_UTC')
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('INVALID_NDR_SELECTION_UTC') from exc
    if (not isinstance(value, datetime) or value.tzinfo is None
            or value.utcoffset() is None or value.utcoffset().total_seconds() != 0):
        raise ValueError('INVALID_NDR_SELECTION_UTC')
    return value.astimezone(timezone.utc)


def select_rows(rows, *, captured_utc, limit):
    """Return selected original rows and the exact recomputable selection plan.

    Caller must validate full row identities and index bytes first. This helper
    checks bounded unique fixed IDs and never examines scores, dates, team names,
    predictions, fetch outcomes or a caller-provided cursor.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_REQUESTS:
        raise ValueError('INVALID_NDR_SELECTION_LIMIT')
    current = _utc(captured_utc)
    if not isinstance(rows, list) or len(rows) > MAX_COHORT:
        raise ValueError('INVALID_NDR_SELECTION_COHORT')
    by_id = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('INVALID_NDR_SELECTION_ROW')
        fixture_id = row.get('provider_fixture_id')
        if not isinstance(fixture_id, str) or not PROVIDER_ID.fullmatch(fixture_id):
            raise ValueError('INVALID_NDR_SELECTION_ID')
        if fixture_id in by_id:
            raise ValueError('DUPLICATE_NDR_SELECTION_ID')
        by_id[fixture_id] = row
    ordered_ids = sorted(by_id, key=int)
    count = len(ordered_ids)
    start = (current.date().toordinal() * limit) % count if count else 0
    selected_ids = [ordered_ids[(start + offset) % count]
                    for offset in range(min(limit, count))]
    digest_input = json.dumps(ordered_ids, ensure_ascii=True,
                              separators=(',', ':')).encode('ascii')
    selection = {
        'policy': POLICY, 'order': ORDER, 'day_utc': current.date().isoformat(),
        'request_limit': limit, 'cohort_count': count,
        'cohort_sha256': hashlib.sha256(digest_input).hexdigest(),
        'start_index': start, 'selected_fixture_ids': selected_ids,
    }
    return [by_id[fixture_id] for fixture_id in selected_ids], selection
