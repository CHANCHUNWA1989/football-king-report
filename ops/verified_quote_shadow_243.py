"""Match an observed quote to a model scenario; never certify betting."""
from datetime import datetime, timezone
from asian_ev_arithmetic_243 import calculate


def _utc(value):
    if not isinstance(value, str):
        raise ValueError('INVALID_TIMESTAMP')
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('INVALID_TIMESTAMP') from exc
    if d.tzinfo is None:
        raise ValueError('NAIVE_TIMESTAMP')
    return d.astimezone(timezone.utc)


def shadow_ev(quote, model, *, captured_utc, max_age_seconds=120):
    """Strict match: event, market, line, side, timestamps and model provenance."""
    hold = {'status': 'HOLD', 'production_recommendations': 'DISABLED',
            'executable_odds_verified': False, 'model_calibrated': False}
    if not isinstance(quote, dict) or not isinstance(model, dict):
        return dict(hold, reason='MISSING_EVIDENCE')
    fields = ('event_id', 'market', 'point', 'outcome')
    if any(quote.get(k) != model.get(k) or quote.get(k) is None for k in fields):
        return dict(hold, reason='IDENTITY_OR_MARKET_MISMATCH')
    if quote['market'] != 'spreads' or quote.get('status') != 'FRESH_OBSERVATION_NOT_EXECUTABLE':
        return dict(hold, reason='UNSUPPORTED_QUOTE')
    if type(max_age_seconds) is not int or not 30 <= max_age_seconds <= 900:
        return dict(hold, reason='INVALID_FRESHNESS_POLICY')
    try:
        captured = _utc(captured_utc)
        updated = _utc(quote['market_last_update_utc'])
        kickoff = _utc(quote['kickoff_utc'])
        predicted = _utc(model['predicted_at_utc'])
    except (KeyError, ValueError, TypeError):
        return dict(hold, reason='INVALID_TIME_EVIDENCE')
    if not 0 <= (captured - updated).total_seconds() <= max_age_seconds:
        return dict(hold, reason='STALE_QUOTE')
    if not predicted <= updated <= captured < kickoff:
        return dict(hold, reason='LOOKAHEAD_OR_INPLAY')
    if model.get('probability_source') != 'independent_pre_match_model':
        return dict(hold, reason='NO_INDEPENDENT_MODEL_PROVENANCE')
    try:
        value = calculate(model['grade_probabilities'], quote['decimal_odds'])
    except (KeyError, ValueError, TypeError):
        return dict(hold, reason='INVALID_EV_INPUT')
    return dict(value, reason='SHADOW_ONLY_NOT_EXECUTABLE',
                event_id=quote['event_id'], market=quote['market'],
                outcome=quote['outcome'], point=quote['point'])
