"""Bind complete same-response h2h research observations to v2 evidence.

No I/O, provider calls, model probabilities or source authentication. Raw records
belong only in the existing ephemeral private runner workspace. Derived IDs are
local observation identities, never native provider quote IDs.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

from ops.asian_ev_quote_provenance import research_evidence_record
from ops.odds_market import SPORTS

FEED_SCHEMA = 'football-king-bound-h2h-feed-v1'
PROVIDER = 'the_odds_api_v4'
ID_KIND = 'DERIVED_COMPOSITE_NOT_PROVIDER_NATIVE'
MAX_EVENTS, MAX_BOOKS, MAX_MARKETS = 500, 100, 20
# Match the existing screener/public-counter capacity. A larger response or
# aggregate batch is rejected wholesale, never sliced into a partial market.
MAX_ROWS = 100000
MAX_AGE = timedelta(minutes=20)
ROW_FIELDS = frozenset(('fixture_id','league','sport_key','home','away','market',
                        'selection','line','decimal_odds','source','provider',
                        'observed_utc','captured_utc','kickoff_utc','source_verified',
                        'independently_calibrated','lineup_checked','schema',
                        'quote_id_kind','evidence'))


def _time(value):
    if isinstance(value,str):
        value = datetime.fromisoformat(value.replace('Z','+00:00'))
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('INVALID_TIME')
    return value.astimezone(timezone.utc)


def _clock(value, reason):
    if not isinstance(value,datetime):
        raise ValueError(reason)
    try:
        return _time(value)
    except (ValueError,TypeError,OverflowError) as exc:
        raise ValueError(reason) from exc


def _identity(value):
    return isinstance(value,str) and bool(value.strip())


def _price(value):
    try:
        return type(value) in (float,int) and math.isfinite(value) and 1.01 <= value <= 100
    except OverflowError:
        return False


def _json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def _canonical(row):
    """Rebuild all semantics and derived identity; trust no supplied digest/ID."""
    if (not isinstance(row,dict) or set(row) != ROW_FIELDS
            or row.get('schema') != FEED_SCHEMA or row.get('provider') != PROVIDER
            or row.get('quote_id_kind') != ID_KIND or row.get('market') != 'h2h'
            or type(row.get('line')) is not int or row['line'] != 0
            or any(row.get(k) is not False for k in
                   ('source_verified','independently_calibrated','lineup_checked'))):
        raise ValueError('INVALID_BOUND_ROW')
    if any(not _identity(row.get(k)) for k in
           ('fixture_id','league','sport_key','home','away','source')):
        raise ValueError('INVALID_BOUND_IDENTITY')
    if (SPORTS.get(row['league']) != row['sport_key'] or row['home'].casefold() == row['away'].casefold()
            or len({row['home'],row['away'],'Draw'}) != 3 or not _price(row['decimal_odds'])):
        raise ValueError('INVALID_BOUND_IDENTITY_OR_PRICE')
    sides = {row['home']:'HOME','Draw':'DRAW',row['away']:'AWAY'}
    if not isinstance(row.get('selection'),str) or row['selection'] not in sides:
        raise ValueError('INVALID_BOUND_SIDE')
    if any(not isinstance(row[k],str) for k in ('observed_utc','captured_utc','kickoff_utc')):
        raise ValueError('INVALID_BOUND_TIME_TYPE')
    updated,captured,kickoff = (_time(row[k]) for k in ('observed_utc','captured_utc','kickoff_utc'))
    if not (timedelta(0) <= captured-updated <= MAX_AGE
            and captured+timedelta(minutes=10) < kickoff < captured+timedelta(days=7)):
        raise ValueError('INVALID_BOUND_TIME_ORDER')
    namespace = [row[k] for k in ('league','sport_key','fixture_id','home','away')]
    identity = {'fixture':namespace,'bookmaker':row['source'],'market':'h2h',
                'selection':sides[row['selection']], 'updated':updated.isoformat(),
                'captured':captured.isoformat()}
    local_id = 'derived:'+hashlib.sha256(_json(identity).encode('utf-8')).hexdigest()
    return {'fixture_id':_json(namespace),'market_id':'h2h','source':PROVIDER,
            'source_quote_id':local_id,'bookmaker_id':row['source'],
            'selection':sides[row['selection']],'market_type':'h2h','line':None,
            'decimal_odds':row['decimal_odds'],'observed_at_utc':captured,
            'bookmaker_updated_at_utc':updated,'kickoff_utc':kickoff}


def bind_response(events, *, league, sport, captured):
    """Consume the existing response once; return complete bound groups only."""
    captured = _clock(captured,'INVALID_CAPTURE_CLOCK')
    if not _identity(league) or not _identity(sport) or SPORTS.get(league) != sport:
        raise ValueError('INVALID_LEAGUE_SPORT')
    rejected = Counter()
    rows = []
    if not isinstance(events,list) or len(events)>MAX_EVENTS:
        return {'quotes':[], 'rejected':{'INVALID_RESPONSE_SHAPE':1}}
    event_counts = Counter(e.get('id') for e in events
                           if isinstance(e,dict) and _identity(e.get('id')))
    for event in events:
        if not isinstance(event,dict):
            rejected['INVALID_EVENT'] += 1
            continue
        eid,home,away = (event.get(k) for k in ('id','home_team','away_team'))
        if (not all(_identity(x) for x in (eid,home,away)) or event.get('sport_key') != sport
                or home.casefold() == away.casefold() or len({home,away,'Draw'}) != 3
                or event.get('completed') is True or event.get('is_outright') is True):
            rejected['INVALID_EVENT_IDENTITY'] += 1
            continue
        if event_counts[eid] != 1:
            rejected['DUPLICATE_EVENT_ID'] += 1
            continue
        try:
            if not isinstance(event.get('commence_time'),str):
                raise ValueError('BAD_KICKOFF_TYPE')
            kickoff = _time(event.get('commence_time'))
            if not captured+timedelta(minutes=10) < kickoff < captured+timedelta(days=7):
                raise ValueError('BAD_KICKOFF')
        except (ValueError,TypeError,OverflowError):
            rejected['INVALID_EVENT_KICKOFF'] += 1
            continue
        books = event.get('bookmakers')
        if not isinstance(books,list) or len(books)>MAX_BOOKS:
            rejected['INVALID_BOOKMAKER_SCOPE'] += 1
            continue
        book_counts = Counter(b.get('key') for b in books
                              if isinstance(b,dict) and _identity(b.get('key')))
        for book in books:
            if not isinstance(book,dict) or not _identity(book.get('key')):
                rejected['INVALID_BOOKMAKER_ID'] += 1
                continue
            if book_counts[book['key']] != 1:
                rejected['DUPLICATE_BOOKMAKER'] += 1
                continue
            markets = book.get('markets')
            if not isinstance(markets,list) or len(markets)>MAX_MARKETS:
                rejected['INVALID_MARKET_SCOPE'] += 1
                continue
            h2h = [m for m in markets if isinstance(m,dict) and m.get('key') == 'h2h']
            if len(h2h) != 1:
                rejected['MISSING_OR_DUPLICATE_H2H'] += 1
                continue
            market = h2h[0]
            if (market.get('period') not in (None,'full','full_game','ft')
                    or market.get('suspended_at') is not None):
                rejected['INVALID_H2H_PHASE'] += 1
                continue
            try:
                # No bookmaker-level clock fallback and no future-time tolerance.
                if not isinstance(market.get('last_update'),str):
                    raise ValueError('BAD_CLOCK_TYPE')
                updated = _time(market.get('last_update'))
                if not timedelta(0) <= captured-updated <= MAX_AGE:
                    raise ValueError('BAD_CLOCK')
            except (ValueError,TypeError,OverflowError):
                rejected['INVALID_MARKET_CLOCK'] += 1
                continue
            outcomes = market.get('outcomes')
            if (not isinstance(outcomes,list) or len(outcomes) != 3
                    or any(not isinstance(o,dict) or not isinstance(o.get('name'),str)
                           or o.get('point') is not None or not _price(o.get('price')) for o in outcomes)
                    or Counter(o['name'] for o in outcomes) != Counter((home,'Draw',away))):
                rejected['INVALID_H2H_OUTCOMES'] += 1
                continue
            group = []
            try:
                for outcome in outcomes:
                    row = {'fixture_id':eid,'league':league,'sport_key':sport,'home':home,'away':away,
                           'market':'h2h','selection':outcome['name'],'line':0,
                           'decimal_odds':outcome['price'],'source':book['key'],'provider':PROVIDER,
                           'observed_utc':updated.isoformat(),'captured_utc':captured.isoformat(),
                           'kickoff_utc':kickoff.isoformat(),'source_verified':False,
                           'independently_calibrated':False,'lineup_checked':False,
                           'schema':FEED_SCHEMA,'quote_id_kind':ID_KIND,'evidence':{}}
                    row['evidence'] = research_evidence_record(_canonical(row))
                    group.append(row)
            except (ValueError,TypeError,OverflowError):
                rejected['INVALID_CANONICAL_EVIDENCE'] += 1
                continue
            rows.extend(group)
            if len(rows)>MAX_ROWS:
                rejected['BOUND_RESPONSE_ROW_LIMIT'] += 1
                return {'quotes':[], 'rejected':dict(sorted(rejected.items()))}
    return {'quotes':rows,'rejected':dict(sorted(rejected.items()))}


def verify_bound_quotes(rows, *, now):
    """Rebuild expected v2 evidence and require complete current three-side groups.

    A locally reproducible digest is tamper detection, not provider authentication.
    """
    now = _clock(now,'INVALID_VERIFICATION_CLOCK')
    if not isinstance(rows,list) or len(rows)>MAX_ROWS:
        return [],{'INVALID_BOUND_ROWS':1}
    rejected = Counter()
    groups = defaultdict(list)
    for row in rows:
        try:
            canonical = _canonical(row)
            if (not isinstance(row['evidence'],dict)
                    or row['evidence'].get('independently_verified') is not False
                    or row['evidence'] != research_evidence_record(canonical)):
                raise ValueError('EVIDENCE_MISMATCH')
            if not (canonical['observed_at_utc'] <= now < canonical['kickoff_utc']
                    and timedelta(0) <= now-canonical['bookmaker_updated_at_utc'] <= MAX_AGE):
                raise ValueError('BOUND_QUOTE_NOT_CURRENT')
            key = (row['league'],row['sport_key'],row['fixture_id'],row['home'],row['away'],
                   row['source'],canonical['bookmaker_updated_at_utc'],
                   canonical['observed_at_utc'],canonical['kickoff_utc'])
            groups[key].append(row)
        except (ValueError,TypeError,KeyError,OverflowError):
            rejected['INVALID_BOUND_EVIDENCE_OR_TIME'] += 1
            continue
    accepted = []
    for group in groups.values():
        home,away = group[0]['home'],group[0]['away']
        if len(group) != 3 or Counter(q['selection'] for q in group) != Counter((home,'Draw',away)):
            rejected['INCOMPLETE_OR_DUPLICATE_BOUND_GROUP'] += 1
            continue
        accepted.extend(group)
    return accepted,dict(sorted(rejected.items()))
