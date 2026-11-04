"""Five-grade Asian handicap EV arithmetic for offline research only."""
import math

GRADES = ('FULL_WIN', 'HALF_WIN', 'PUSH', 'HALF_LOSS', 'FULL_LOSS')


def calculate(probabilities, decimal_odds):
    """Return a hypothetical EV without certifying prices or recommendations."""
    if type(decimal_odds) not in (int, float) or not math.isfinite(decimal_odds) or not 1.01 <= decimal_odds <= 100:
        raise ValueError('INVALID_ODDS')
    if not isinstance(probabilities, dict) or set(probabilities) != set(GRADES):
        raise ValueError('INVALID_GRADES')
    if any(type(probabilities[k]) not in (int, float) or not math.isfinite(probabilities[k]) or not 0 <= probabilities[k] <= 1 for k in GRADES):
        raise ValueError('INVALID_PROBABILITY')
    if not math.isclose(sum(probabilities.values()), 1, abs_tol=1e-6, rel_tol=0):
        raise ValueError('INVALID_PROBABILITY_SUM')
    gain = (decimal_odds - 1) * (probabilities['FULL_WIN'] + probabilities['HALF_WIN'] / 2)
    loss = probabilities['FULL_LOSS'] + probabilities['HALF_LOSS'] / 2
    return {'hypothetical_ev': round(gain - loss, 8), 'status': 'HOLD', 'research_only': True,
            'executable_odds_verified': False, 'model_calibrated': False,
            'production_recommendations': 'DISABLED'}
