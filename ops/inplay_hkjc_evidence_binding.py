"""Fail-closed, offline, research-only point-in-time binding of three claims.

Connects a PRE-SEALED provider fixture mapping, 2 source score assertions,
a human-reviewed image digest and a claimed HKJC three-way quote. Neither
asserted source clocks nor an image hash authenticate upstream publication,
image contents, bookability, odds or any model's forecast. No EV is computed.
"""
from datetime import timedelta
import hashlib
import json
import math
from urllib.parse import urlparse

from live_score_identity_guard import check as check_live_scores, parse_utc
from screenshot_evidence_intake import intake as check_screenshot

SCHEMA = 'football-king-inplay-hkjc-evidence-binding-research-v1'
PERIODS = {'FIRST_HALF', 'HALF_TIME', 'SECOND_HALF'}
FORBIDDEN = {'final_score', 'score_ft', 'result', 'settlement',
             'positive_ev_verified', 'model_probability', 'certified'}


def _valid_id(x):
    return (type(x) is str and 1 <= len(x) <= 128 and x == x.strip()
            and x.isascii() and all(c.isalnum() or c in '_-:.' for c in x))


def _url_host(value, pinned_host):
    if type(value) is not str or type(pinned_host) is not str:
        return False
    try:
        u = urlparse(value)
        return (u.scheme == 'https' and u.hostname == pinned_host
                and u.username is None and u.password is None
                and u.port is None and not u.fragment and bool(u.path))
    except ValueError:
        return False


def _nonnegative_int(x, high):
    return type(x) is int and 0 <= x <= high


def _block(reason):
    return {
        'schema': SCHEMA, 'status': 'HOLD', 'reason': reason,
        'decision': 'HOLD', 'production_recommendations': 'DISABLED',
        'research_only': True, 'structure_consistent': False,
        'independent_sources_authenticated': False,
        'screenshot_content_verified': False,
        'quote_matches_image_verified': False,
        'bookmaker_price_executable_verified': False,
        'point_in_time_externally_attested': False,
        'model_scoring_eligible': False, 'positive_ev_verified': False,
        'probabilities_calibrated': False, 'recommendation': None,
        'stakes': None, 'roi': None, 'certified_forward_samples': 0,
        'candidate_manifest': None,
    }


def audit(fixture, observations, quote, screenshot_bytes, screenshot_manifest, decision_utc):
    """Bind declared records; never confer trust even if structure is valid."""
    try:
        if (type(fixture) is not dict or type(quote) is not dict
                or type(observations) is not list or type(screenshot_manifest) is not dict):
            raise ValueError('INVALID_INPUT')
        if any(FORBIDDEN & set(r) for r in [fixture, quote, screenshot_manifest]
               if type(r) is dict):
            raise ValueError('FUTURE_OR_CERTIFICATION_INPUT_REJECTED')
        if any(type(r) is not dict or FORBIDDEN & set(r) for r in observations):
            raise ValueError('FUTURE_OR_CERTIFICATION_INPUT_REJECTED')
        event_id = fixture.get('fixture_id')
        bookmaker_event_id = fixture.get('bookmaker_event_id')
        if not _valid_id(event_id) or not _valid_id(bookmaker_event_id):
            raise ValueError('MISSING_PRESEALED_FIXTURE_BINDING')
        display = fixture.get('screenshot_labels')
        if (type(display) is not dict or set(display) != {'league', 'home', 'away'}
                or not all(type(v) is str and 0 < len(v.strip()) <= 120
                           and v == v.strip() for v in display.values())
                or display['home'] == display['away']):
            raise ValueError('MISSING_PRESEALED_DISPLAY_BINDING')
        if not _valid_id(fixture.get('bookmaker_id')):
            raise ValueError('MISSING_PRESEALED_BOOKMAKER')
        if type(fixture.get('bookmaker_host')) is not str:
            raise ValueError('MISSING_PRESEALED_BOOKMAKER_HOST')
        now = parse_utc(decision_utc)
        kickoff = parse_utc(fixture.get('kickoff_utc'))
        if not kickoff < now < kickoff + timedelta(hours=3):
            raise ValueError('NOT_IN_LIVE_WINDOW')
        score_result = check_live_scores(fixture, observations, decision_utc)
        if score_result['status'] != 'RESEARCH_ONLY':
            raise ValueError('SOURCE_GATE_HOLD:' + score_result.get('reason', 'UNKNOWN'))
        if score_result.get('match_status') not in PERIODS:
            raise ValueError('PREMATCH_OR_FINISHED_IS_NOT_LIVE')
        if score_result.get('model_scoring_eligible') is not False:
            raise ValueError('UNSAFE_SCORE_GATE')
        sc = check_screenshot(screenshot_bytes, screenshot_manifest, now=now)
        if sc['status'] != 'RESEARCH_ONLY':
            raise ValueError('SCREENSHOT_GATE_HOLD:' + ','.join(sc.get('blockers', [])))
        sf = sc['case']['fixture']
        ss = sc['case']['screenshot']
        if sf['event_id'] != bookmaker_event_id:
            raise ValueError('BOOKMAKER_SCREENSHOT_EVENT_CONFLICT')
        if any(sf[k] != display[k] for k in ('league', 'home', 'away')):
            raise ValueError('SCREENSHOT_DISPLAY_FIXTURE_CONFLICT')
        if (ss['home_goals'] != score_result['score_home']
                or ss['away_goals'] != score_result['score_away']):
            raise ValueError('SCREENSHOT_SCORE_CONFLICT')
        minute = ss['minute']
        period = score_result['match_status']
        if ((period == 'FIRST_HALF' and not minute < 45)
                or (period == 'HALF_TIME' and minute != 45)
                or (period == 'SECOND_HALF' and not 45 < minute < 90)):
            raise ValueError('SCREENSHOT_PERIOD_CONFLICT')
        observed = parse_utc(ss['observed_at_utc'])
        wall_minutes = (observed - kickoff).total_seconds() / 60
        if not minute - 4 <= wall_minutes <= minute + 24:
            raise ValueError('IMPOSSIBLE_SCREENSHOT_GAME_CLOCK')
        if len(observations) < 2:
            raise ValueError('INSUFFICIENT_SCORE_OBSERVATIONS')
        upstream_updates = []
        material_times = []
        for obs in observations:
            src_update = parse_utc(obs.get('source_updated_utc'))
            captured = parse_utc(obs.get('captured_utc'))
            material = parse_utc(obs.get('last_material_event_utc'))
            if (not kickoff <= material <= src_update <= captured <= now
                    or now - src_update > timedelta(seconds=90)):
                raise ValueError('SOURCE_UPDATE_OR_EVENT_TOO_OLD')
            if (type(obs.get('elapsed_regulation_minutes')) not in (int, float)
                    or not math.isfinite(obs['elapsed_regulation_minutes'])
                    or abs(obs['elapsed_regulation_minutes'] - minute) > 1):
                raise ValueError('CROSS_SOURCE_MATCH_MINUTE_CONFLICT')
            if (not _nonnegative_int(obs.get('home_red_cards'), 5)
                    or not _nonnegative_int(obs.get('away_red_cards'), 5)):
                raise ValueError('RED_CARD_EVIDENCE_MISSING')
            if obs['home_red_cards'] or obs['away_red_cards']:
                raise ValueError('RED_CARD_EFFECT_UNMODELLED')
            upstream_updates.append(src_update)
            material_times.append(material)
        if len(set(material_times)) != 1:
            raise ValueError('MATERIAL_EVENT_TIMES_CONFLICT')
        if (max(upstream_updates) - min(upstream_updates)) > timedelta(seconds=90):
            raise ValueError('CROSS_SOURCE_TIME_DRIFT')
        if (quote.get('fixture_id') != event_id
                or quote.get('bookmaker_event_id') != bookmaker_event_id
                or quote.get('bookmaker_id') != fixture['bookmaker_id']):
            raise ValueError('QUOTE_FIXTURE_OR_BOOKMAKER_CONFLICT')
        if not _url_host(quote.get('source_url'), fixture['bookmaker_host']):
            raise ValueError('UNBOUND_BOOKMAKER_URL')
        if quote.get('market') != 'HKJC_THREE_WAY_HANDICAP':
            raise ValueError('UNSUPPORTED_THREE_WAY_MARKET')
        if quote.get('selection') not in ('HOME', 'DRAW', 'AWAY'):
            raise ValueError('INVALID_THREE_WAY_SELECTION')
        line = quote.get('home_handicap')
        price = quote.get('decimal_price')
        if (type(line) is not int or not -3 <= line <= 3
                or type(price) not in (int, float) or not math.isfinite(price)
                or not 1 < price <= 500):
            raise ValueError('INVALID_THREE_WAY_QUOTE')
        if quote.get('in_play') is not True:
            raise ValueError('QUOTE_NOT_IN_PLAY')
        quote_updated = parse_utc(quote.get('upstream_updated_utc'))
        quote_capture = parse_utc(quote.get('captured_utc'))
        if (not max(material_times) <= quote_updated <= quote_capture <= now
                or now - quote_updated > timedelta(seconds=90)):
            raise ValueError('STALE_OR_PRE_EVENT_QUOTE')
        if abs((quote_capture - observed).total_seconds()) > 90:
            raise ValueError('QUOTE_SCREENSHOT_NOT_SAME_CUT')
        digest = hashlib.sha256(screenshot_bytes).hexdigest()
        if quote.get('image_sha256') != digest:
            raise ValueError('QUOTE_SCREENSHOT_HASH_CONFLICT')
        # Synthetic self-declared hash only; no TSA, witness or official capture receipt.
        receipt = {
            'schema': SCHEMA, 'fixture_id': event_id,
            'bookmaker_event_id': bookmaker_event_id,
            'provider_ids': dict(sorted(fixture['provider_event_ids'].items())),
            'image_sha256': digest,
            'score': [score_result['score_home'], score_result['score_away']],
            'minute': minute, 'match_status': period,
            'as_of_utc': now.isoformat(),
            'screenshot_claimed_utc': observed.isoformat(),
            'quote_claimed_update_utc': quote_updated.isoformat(),
            'quote_claimed_capture_utc': quote_capture.isoformat(),
            'source_claimed_update_utc': sorted(t.isoformat() for t in upstream_updates),
            'last_material_event_claimed_utc': material_times[0].isoformat(),
            'market': quote['market'], 'selection': quote['selection'],
            'home_handicap': line, 'claimed_decimal_price': price,
        }
        packed = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False)
        receipt['sha256_self_declared_not_attested'] = hashlib.sha256(packed.encode()).hexdigest()
        return {
            **_block('STRUCTURE_ONLY_NO_SOURCE_AUTHENTICATION'),
            'status': 'RESEARCH_ONLY', 'structure_consistent': True,
            'candidate_manifest': receipt,
        }
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        return _block(str(exc) or 'INVALID_EVIDENCE')
