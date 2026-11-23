"""Explain uncalibrated per-league Shadow coverage gaps without altering forecasts.

Counts only the rows the unchanged shadow_forecast predictor saw. This does not
certify publisher identity, schedule, historical data, calibrated odds, or EV.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HK = ZoneInfo('Asia/Hong_Kong')


def _precise_time(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, OverflowError):
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo is not None else None


def summarize(rows, predictions, now):
    """Provide descriptive counters, never eligibility authorisation.

    `predictions` is the existing model output. The diagnostic never changes
    its content, adds inferred kickoffs, or merges provider identities.
    """
    if (not isinstance(rows, list) or not isinstance(predictions, list)
            or not isinstance(now, datetime) or now.tzinfo is None):
        raise ValueError('INVALID_SHADOW_DIAGNOSTIC_INPUT')
    today = now.astimezone(HK).date()
    counts = {
        'received_rows': len(rows),
        'prior_finished_score_rows': 0,
        'scheduled_rows': 0,
        'scheduled_missing_precise_utc': 0,
        'scheduled_invalid_or_outside_window': 0,
        'scheduled_valid_precise_utc': 0,
        'predictions_emitted': len(predictions),
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            match_day = date.fromisoformat(row['date'])
        except (KeyError, ValueError, TypeError):
            match_day = None
        home, away = row.get('home'), row.get('away')
        teams_ok = (isinstance(home, str) and isinstance(away, str)
                    and 0 < len(home) < 110 and 0 < len(away) < 110 and home != away)
        score = row.get('score_ft')
        if (teams_ok and match_day is not None and match_day < today
                and row.get('status') == 'FINISHED' and isinstance(score, list)
                and len(score) == 2 and all(type(g) is int and 0 <= g <= 20 for g in score)):
            counts['prior_finished_score_rows'] += 1
        if row.get('status') != 'SCHEDULED' or score is not None:
            continue
        counts['scheduled_rows'] += 1
        kickoff = _precise_time(row.get('kickoff_utc'))
        if kickoff is None:
            counts['scheduled_missing_precise_utc'] += 1
        elif (not teams_ok or match_day is None or kickoff.astimezone(HK).date() != match_day
              or not now + timedelta(minutes=10) < kickoff
              or match_day > today + timedelta(days=21)):
            counts['scheduled_invalid_or_outside_window'] += 1
        else:
            counts['scheduled_valid_precise_utc'] += 1
    if counts['predictions_emitted']:
        reason = 'UNCALIBRATED_SHADOW_PREDICTIONS_ONLY'
    elif counts['scheduled_rows'] == 0:
        reason = 'NO_UNPLAYED_SCHEDULED_ROWS'
    elif counts['scheduled_valid_precise_utc'] == 0:
        reason = 'NO_ELIGIBLE_PRECISE_KICKOFF_ROWS'
    elif counts['prior_finished_score_rows'] < 30:
        reason = 'FEWER_THAN_30_PRIOR_FINISHED_SCORE_ROWS'
    else:
        reason = 'ZERO_FORECAST_WITH_VALID_SCHEDULE_REVIEW_TRAINING_OR_IDENTITY'
    return {
        'schema': 'football-king-shadow-source-coverage-diagnostic-v1',
        'status': 'SHADOW_ONLY' if predictions else 'HOLD',
        'reason': reason,
        'observed_row_counts_not_an_independent_source_attestation': True,
        'source_utc_authenticated': False,
        'independently_validated_result_rows': 0,
        'calibrated_model': False,
        'verified_positive_ev': False,
        'production_recommendations': 'DISABLED',
        **counts,
    }
