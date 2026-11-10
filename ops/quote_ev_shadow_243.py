"""Fail-closed research bridge between a quote snapshot and grade probabilities."""
from asian_ev_arithmetic_243 import calculate


def evaluate(quote_report, *, event_id, bookmaker, market, outcome, point, probabilities):
    """Match exact quote identity; return HOLD regardless of hypothetical EV."""
    result = {'status': 'HOLD', 'production_recommendations': 'DISABLED',
              'reason': 'NO_EXACT_FRESH_QUOTE', 'hypothetical_ev': None,
              'independent_model_verified': False, 'executable_odds_verified': False}
    if not isinstance(quote_report, dict) or quote_report.get('status') != 'RESEARCH_ONLY':
        return result
    if type(point) not in (int, float) or type(event_id) is not str or not event_id:
        return result
    matches = [q for q in quote_report.get('quotes', []) if isinstance(q, dict)
               and q.get('event_id') == event_id and q.get('bookmaker') == bookmaker
               and q.get('market') == market and q.get('outcome') == outcome
               and type(q.get('point')) in (int, float) and q.get('point') == point
               and q.get('quote_pre_match_at_capture') is True
               and q.get('status') == 'FRESH_OBSERVATION_NOT_EXECUTABLE']
    if len(matches) != 1:
        result['reason'] = 'QUOTE_IDENTITY_OR_PHASE_MISMATCH'
        return result
    if market != 'spreads':
        result['reason'] = 'UNSUPPORTED_EV_MARKET'
        return result
    try:
        ev = calculate(probabilities, matches[0]['decimal_odds'])
    except (ValueError, KeyError, TypeError):
        result['reason'] = 'INVALID_MODEL_OR_QUOTE'
        return result
    result['hypothetical_ev'] = ev['hypothetical_ev']
    result['reason'] = 'UNVERIFIED_EXECUTABILITY_AND_MODEL_CALIBRATION'
    return result
