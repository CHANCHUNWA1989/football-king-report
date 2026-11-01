"""Fail-closed two-publisher final-score research gate.

This module does not authenticate publisher independence, official decisions,
model predictions, bookmaker settlements, prices or positive EV.
"""
from urllib.parse import urlparse

ALLOWED_STATUSES = frozenset({"FT", "ABANDONED", "POSTPONED", "LIVE", "SUSPENDED"})


def _hold(reason):
    return {
        "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "score_agreement": False, "upstream_independence_certified": False,
        "bookmaker_settlement_eligible": False,
        "model_scoring_eligible": False,
    }


def reconcile_two_published_results(observations):
    """Only two consistent *regular full-time* reports may be compared.

    Abandoned matches (even 4-0) must be reviewed separately against a
    governing body's decision and bookmaker-specific settlement rules.
    """
    if not isinstance(observations, list) or len(observations) != 2:
        return _hold("NEED_EXACTLY_TWO_PUBLISHERS")
    seen_publishers, seen_hosts = set(), set()
    identity = None
    scores = []
    statuses = []
    for row in observations:
        if not isinstance(row, dict):
            return _hold("INVALID_OBSERVATION")
        provider, url = row.get("publisher"), row.get("source_url")
        if not isinstance(provider, str) or not provider.strip() or not isinstance(url, str):
            return _hold("MISSING_SOURCE_PROVENANCE")
        try:
            parts = urlparse(url)
            invalid_url = (parts.scheme != "https" or not parts.hostname
                           or parts.username or parts.password
                           or parts.port is not None)
        except ValueError:
            return _hold("INVALID_SOURCE_URL")
        if invalid_url:
            return _hold("INVALID_SOURCE_URL")
        if provider in seen_publishers or parts.hostname in seen_hosts:
            return _hold("DUPLICATE_SOURCE")
        seen_publishers.add(provider)
        seen_hosts.add(parts.hostname)
        fixture = tuple(row.get(k) for k in
                        ("league", "home", "away", "kickoff_utc"))
        if not all(type(value) is str and value for value in fixture):
            return _hold("MISSING_FIXTURE_IDENTITY")
        if identity is not None and identity != fixture:
            return _hold("FIXTURE_IDENTITY_CONFLICT")
        identity = fixture
        h, a = row.get("home_goals"), row.get("away_goals")
        if type(h) is not int or type(a) is not int or min(h, a) < 0:
            return _hold("INVALID_SCORE")
        status = row.get("match_status")
        if type(status) is not str or status not in ALLOWED_STATUSES:
            return _hold("INVALID_MATCH_STATUS")
        scores.append((h, a))
        statuses.append(status)
    if scores[0] != scores[1]:
        return _hold("CROSS_SOURCE_SCORE_CONFLICT")
    if "ABANDONED" in statuses or "SUSPENDED" in statuses:
        return _hold("ABANDONED_OR_SUSPENDED_REQUIRES_OFFICIAL_DECISION")
    if statuses != ["FT", "FT"]:
        return _hold("NOT_BOTH_REGULAR_FULL_TIME")
    return {
        "status": "RESEARCH_ONLY",
        "reason": "TWO_PUBLISHERS_AGREE_NOT_INDEPENDENT_AUTHENTICATION",
        "production_recommendations": "DISABLED",
        "score_agreement": True,
        "home_goals": scores[0][0], "away_goals": scores[0][1],
        "upstream_independence_certified": False,
        "bookmaker_settlement_eligible": False,
        "model_scoring_eligible": False,
    }
