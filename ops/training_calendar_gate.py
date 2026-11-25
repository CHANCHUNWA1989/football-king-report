"""Conservative calendar coverage check, NOT independent training certification."""

MIN_REFERENCE_COVERAGE = 0.95
MAX_ROWS = 3000


def audit(reference_ids, observed_ids):
    """IDs must already be explicitly matched to the same reference calendar.

    No matching, score verification, model fitting or source authentication.
    A reference calendar can include postponed games and ambiguous cutoff days.
    """
    for rows in (reference_ids, observed_ids):
        if (not isinstance(rows, list) or len(rows) > MAX_ROWS
                or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in rows)):
            raise ValueError('INVALID_REFERENCE_IDS')
        if len(set(rows)) != len(rows):
            raise ValueError('DUPLICATE_REFERENCE_IDS')
    reference, observed = set(reference_ids), set(observed_ids)
    if not observed <= reference:
        raise ValueError('OBSERVATION_OUTSIDE_REFERENCE')
    n, k = len(reference), len(observed)
    coverage = k / n if n else None
    threshold_met = coverage is not None and coverage >= MIN_REFERENCE_COVERAGE
    return {
        'schema': 'football-king-training-calendar-coverage-v1',
        'status': 'HOLD', 'production_recommendations': 'DISABLED',
        'reference_calendar_count': n, 'matched_observed_count': k,
        'unmatched_reference_count': n-k, 'coverage_fraction': coverage,
        'minimum_research_reference_coverage': MIN_REFERENCE_COVERAGE,
        'reference_coverage_threshold_met': threshold_met,
        'reference_calendar_authenticated_complete': False,
        'independent_result_certification': False,
        'training_admission_authorized': False,
        'reason': ('REFERENCE_COVERAGE_ONLY_REQUIRES_INDEPENDENT_EVIDENCE' if threshold_met
                   else 'INSUFFICIENT_OR_UNKNOWN_REFERENCE_COVERAGE'),
        'missing_reference_ids': sorted(reference-observed),
    }
