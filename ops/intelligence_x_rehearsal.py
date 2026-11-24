"""Offline attempt replay for P25. No fetching, sleeping, scheduling or publication."""
import json
import sys

from intelligence_x_live_evidence import audit_live

MAX_INPUT = 256 * 1024
MAX_ATTEMPTS = 3


def _unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError('DUPLICATE_JSON_KEY')
        out[k] = v
    return out


def _constant(value):
    raise ValueError('INVALID_JSON_CONSTANT')


def replay(request):
    """Accept caller-supplied outage markers followed by at most one data batch.

    Never retry a semantic rejection or select the best of conflicting batches.
    The registry, replay clock and outage markers are not authenticated.
    """
    if type(request) is not dict or request.keys() != {'fixture_id', 'registry', 'now_utc', 'attempts'}:
        raise ValueError('INVALID_REQUEST')
    attempts = request['attempts']
    if type(attempts) is not list or not 1 <= len(attempts) <= MAX_ATTEMPTS:
        raise ValueError('INVALID_ATTEMPTS')
    config = {k: request[k] for k in ('fixture_id', 'registry', 'now_utc')}
    audit_live([], **config)  # Validate the configuration even during total outage.
    unavailable = 0
    result = None
    for i, attempt in enumerate(attempts):
        if type(attempt) is not dict:
            raise ValueError('INVALID_ATTEMPT')
        if attempt == {'kind': 'UNAVAILABLE'}:
            unavailable += 1
        elif (attempt.keys() == {'kind', 'snapshots'} and attempt['kind'] == 'SNAPSHOTS'
              and i == len(attempts)-1):
            result = audit_live(attempt['snapshots'], **config)
        else:
            raise ValueError('INVALID_ATTEMPT_SEQUENCE')
    diagnostic = result['diagnostic'] if result is not None else 'UNAVAILABLE'
    return {'schema': 'intelligence-x-rehearsal-v1', 'input_kind': 'OFFLINE_REPLAY',
            'attempts': len(attempts), 'unavailable_attempts': unavailable,
            'diagnostic': diagnostic, 'status': 'HOLD', 'source_authorized': False,
            'independently_verified': False, 'eligible_for_model_scoring': False,
            'production_recommendations': 'DISABLED', 'external_calls': 0}


def decode(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_INPUT:
        raise ValueError('INVALID_INPUT_SIZE')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique, parse_constant=_constant)


def main():
    try:
        report = replay(decode(sys.stdin.buffer.read(MAX_INPUT + 1)))
    except (ValueError, TypeError, OverflowError, RecursionError):
        print('OFFLINE_REPLAY_REJECTED', file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
