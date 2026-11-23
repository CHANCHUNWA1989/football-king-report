"""Read-only fixture coverage audit for research; never authorizes betting.

Consumes existing *derived* market consensus and immutable research snapshots.
Different-provider IDs are never inferred from team names or kickoff alone.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def utc(raw):
    if not isinstance(raw, str):
        raise ValueError('INVALID_TIMESTAMP')
    try:
        value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('INVALID_TIMESTAMP') from None
    if value.tzinfo is None:
        raise ValueError('NAIVE_TIMESTAMP')
    return value.astimezone(timezone.utc)


def nonnegative_age(now, raw):
    try:
        age = (now - utc(raw)).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return None
    return age if age >= -300 else None


def audit(shadow, market, pairing, collection, *, start, end, now):
    """Summarize fixture-level blockers; no bookmaker prices or EV claims."""
    start, end, now = utc(start), utc(end), utc(now)
    if not start < end or (end-start).total_seconds() > 48*3600:
        raise ValueError('INVALID_WINDOW')
    if not all(isinstance(x, dict) for x in (shadow, market, pairing, collection)):
        raise ValueError('INVALID_DOCUMENT')
    if not isinstance(market.get('events'), list) or not isinstance(shadow.get('predictions'), list):
        raise ValueError('MISSING_SOURCE_ROWS')
    market_age = nonnegative_age(now, market.get('as_of_utc'))
    collection_age = nonnegative_age(now, collection.get('as_of_utc'))
    market_fresh = market_age is not None and market_age <= 4*3600
    collection_ok = (collection.get('collection_status') == 'READY_RESEARCH'
                     and collection_age is not None and collection_age <= 4*3600)
    predictions = shadow['predictions']
    shadow_window = [p for p in predictions if isinstance(p, dict)
                     and _in_window(p.get('kickoff_utc'), start, end)]
    by_id = {}
    for row in predictions:
        if not isinstance(row, dict):
            continue
        identifier = row.get('event_id')
        if isinstance(identifier, str) and identifier:
            by_id.setdefault(identifier, []).append(row)
    # A slate-level matched_count never proves that this *specific* event is paired.
    # This offline diagnostic lacks an independently authenticated event-level bridge.
    slate_has_pairs = (pairing.get('status') in ('READY_RESEARCH', 'RESEARCH_ONLY')
                       and type(pairing.get('matched_count')) is int
                       and pairing['matched_count'] > 0)
    seen = set()
    fixtures = []
    for row in market['events']:
        if not isinstance(row, dict) or not _in_window(row.get('kickoff_utc'), start, end):
            continue
        identifier = row.get('source_event_id')
        if not isinstance(identifier, str) or not identifier:
            continue
        if identifier in seen:
            raise ValueError('DUPLICATE_MARKET_EVENT_ID')
        seen.add(identifier)
        kickoff = utc(row['kickoff_utc'])
        quote_age = nonnegative_age(now, row.get('market_last_update_utc'))
        try:
            quote_time = utc(row.get('market_last_update_utc'))
            batch_time = utc(market.get('as_of_utc'))
            valid_quote_chronology = quote_time <= batch_time and quote_time < kickoff
        except (ValueError, TypeError, OverflowError):
            valid_quote_chronology = False
        # Cross-provider identities require an explicit authenticated bridge.
        # An equal string is only an exact-ID diagnostic, not source certification.
        candidates = by_id.get(identifier, [])
        exact_candidate = (len(candidates) == 1
                           and candidates[0].get('league') == row.get('league')
                           and candidates[0].get('kickoff_utc') == row.get('kickoff_utc')
                           and _earlier(candidates[0].get('prediction_utc'), kickoff))
        blockers = []
        if not market_fresh or quote_age is None or quote_age > 4*3600:
            blockers.append('STALE_OR_INVALID_MARKET_CONSENSUS')
        if not valid_quote_chronology:
            blockers.append('INVALID_QUOTE_CHRONOLOGY')
        if not collection_ok:
            blockers.append('MARKET_COLLECTION_NOT_READY')
        if not exact_candidate:
            blockers.append('NO_EXACT_SOURCE_ID_FORECAST_BRIDGE')
        if not slate_has_pairs:
            blockers.append('NO_MARKET_MODEL_PAIRS_IN_SLATE')
        else:
            blockers.append('EVENT_PAIR_PROVENANCE_UNATTESTED')
        if shadow.get('model_calibrated') is not True:
            blockers.append('MODEL_NOT_CALIBRATED')
        if shadow.get('lineups_confirmed') is not True:
            blockers.append('OFFICIAL_LINEUPS_NOT_ATTESTED')
        if shadow.get('xg_verified') is not True:
            blockers.append('ACTUAL_XG_NOT_ATTESTED')
        # No executable bookmaker prices are included in public market consensus.
        blockers.append('NO_AUTHENTICATED_EXECUTABLE_PRICE')
        fixtures.append({
            'market_source_event_id': identifier, 'league': row.get('league'),
            'home': row.get('home'), 'away': row.get('away'),
            'kickoff_utc': row['kickoff_utc'],
            'model_exact_id_candidate_found': bool(exact_candidate),
            'market_quote_age_seconds': round(quote_age) if quote_age is not None else None,
            'status': 'HOLD', 'blockers': blockers,
            'verified_positive_ev': False,
        })
    fixtures.sort(key=lambda x: (x['kickoff_utc'], x['market_source_event_id']))
    return {
        'schema': 'football-king-fixture-coverage-audit-v1',
        'checked_utc': now.isoformat(), 'window_start_utc': start.isoformat(),
        'window_end_utc': end.isoformat(), 'status': 'HOLD',
        'production_recommendations': 'DISABLED',
        'market_snapshot_as_of_utc': market.get('as_of_utc'),
        'market_snapshot_age_seconds': round(market_age) if market_age is not None else None,
        'collection_status': collection.get('collection_status', 'UNKNOWN'),
        'collection_reason': collection.get('collection_reason'),
        'market_pair_status': pairing.get('status'),
        'market_pair_reason': pairing.get('reason'),
        'window_shadow_predictions': len(shadow_window),
        'window_market_events': len(fixtures), 'certified_fixtures': 0,
        'note': 'Derived 1X2 consensus is not an executable price. No name-based cross-source joining, EV, staking or model promotion.',
        'fixtures': fixtures,
    }


def _in_window(value, start, end):
    try:
        return start <= utc(value) < end
    except (ValueError, TypeError, OverflowError):
        return False


def _earlier(value, kickoff):
    try:
        return utc(value) < kickoff
    except (ValueError, TypeError, OverflowError):
        return False


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('shadow', 'market', 'pairing', 'collection'):
        p.add_argument('--'+name, required=True)
    for name in ('start', 'end'):
        p.add_argument('--'+name+'-utc', required=True)
    p.add_argument('--now-utc')
    p.add_argument('--output', required=True)
    args = p.parse_args(argv)
    docs = [json.loads(Path(getattr(args, k)).read_text(encoding='utf-8'))
            for k in ('shadow', 'market', 'pairing', 'collection')]
    now = args.now_utc or datetime.now(timezone.utc).isoformat()
    result = audit(*docs, start=args.start_utc, end=args.end_utc, now=now)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'window_market_events': result['window_market_events'],
                      'window_shadow_predictions': result['window_shadow_predictions'],
                      'certified_fixtures': 0, 'production_recommendations': 'DISABLED'},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
