"""Fail-closed, zero-network identity gate for research-only live football snapshots.

Two matching provider assertions do not prove authentication, source
independence or a result. This module never certifies settlement, forecasts,
prices, EV or ROI. Intended as a new, isolated, opt-in research sidecar.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

ALLOWED_PROVIDER_HOSTS = {
    "fotmob": frozenset(("www.fotmob.com", "fotmob.com")),
    "sofascore": frozenset(("www.sofascore.com", "sofascore.com")),
    "flashscore": frozenset(("www.flashscore.com", "flashscore.com")),
    "skysports": frozenset(("www.skysports.com", "skysports.com")),
    "guardian": frozenset(("www.theguardian.com", "theguardian.com")),
}
LIVE_STATUSES = frozenset(("FIRST_HALF", "HALF_TIME", "SECOND_HALF"))
ALL_STATUSES = LIVE_STATUSES | frozenset(("NOT_STARTED", "FINISHED", "POSTPONED", "ABANDONED"))
MAX_AGE = timedelta(minutes=10)
MAX_KICKOFF_DRIFT = timedelta(minutes=3)


def parse_utc(value):
    if type(value) is not str:
        raise ValueError("INVALID_UTC_TIMESTAMP")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("NAIVE_TIMESTAMP")
        return instant.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_UTC_TIMESTAMP") from exc


def _valid_id(value):
    return type(value) is str and 1 <= len(value) <= 128 and value == value.strip() and all(
        char.isalnum() or char in "_-:." for char in value
    )


def _valid_fixture(fixture):
    if not isinstance(fixture, dict):
        raise ValueError("INVALID_EXPECTED_FIXTURE")
    if (fixture.get("gender") not in ("men", "women")
            or not all(_valid_id(fixture.get(k)) for k in
                       ("league", "home_id", "away_id"))
            or fixture["home_id"] == fixture["away_id"]):
        raise ValueError("INVALID_EXPECTED_FIXTURE")
    ko = parse_utc(fixture.get("kickoff_utc"))
    sealed = parse_utc(fixture.get("expected_identity_sealed_utc"))
    if sealed >= ko - timedelta(minutes=10):
        raise ValueError("EXPECTED_IDENTITY_NOT_SEALED_PREMATCH")
    ids = fixture.get("provider_event_ids")
    urls = fixture.get("provider_event_urls")
    if (type(ids) is not dict or type(urls) is not dict
            or set(ids) != set(urls)
            or len(ids) < 2
            or len(ids) > len(ALLOWED_PROVIDER_HOSTS)
            or any(provider not in ALLOWED_PROVIDER_HOSTS or not _valid_id(ev_id)
                   for provider, ev_id in ids.items())):
        raise ValueError("MISSING_PRIOR_PROVIDER_IDS")
    return ko, sealed


def check(fixture, observations, as_of_utc):
    """Check declared point-in-time identity; not real feed authentication."""
    hold = {
        "status": "HOLD", "reason": "INVALID_INPUT",
        "production_recommendations": "DISABLED", "model_scoring_eligible": False,
        "independently_authenticated": False, "settlement_certified": False,
        "price_or_positive_ev_certified": False,
    }
    try:
        if (not isinstance(observations, list) or len(observations) < 2
                or len(observations) > len(ALLOWED_PROVIDER_HOSTS)):
            raise ValueError("NEED_AT_LEAST_TWO_OBSERVATIONS")
        ko, sealed = _valid_fixture(fixture)
        now = parse_utc(as_of_utc)
        by_provider = {}
        for obs in observations:
            if not isinstance(obs, dict):
                raise ValueError("BAD_PROVIDER_OBSERVATION")
            provider = obs.get("provider")
            if type(provider) is not str or provider not in fixture["provider_event_ids"]:
                raise ValueError("UNKNOWN_SOURCE_FOR_FIXTURE")
            if provider in by_provider:
                raise ValueError("DUPLICATED_PUBLISHER")
            if obs.get("source_event_id") != fixture["provider_event_ids"][provider]:
                raise ValueError("WRONG_SOURCE_EVENT_ID")
            for field in ("gender", "league", "home_id", "away_id"):
                if obs.get(field) != fixture[field]:
                    raise ValueError("FIXTURE_IDENTITY_CONFLICT:" + field)
            source_ko = parse_utc(obs.get("kickoff_utc"))
            if abs(source_ko - ko) > MAX_KICKOFF_DRIFT:
                raise ValueError("SOURCE_KICKOFF_CONFLICT")
            url = obs.get("source_url")
            if type(url) is not str or type(fixture["provider_event_urls"].get(provider)) is not str:
                raise ValueError("SOURCE_URL_INVALID")
            if url != fixture["provider_event_urls"][provider]:
                raise ValueError("SOURCE_EVENT_URL_MISMATCH")
            parts = urlparse(url)
            if (parts.scheme != "https" or parts.hostname not in ALLOWED_PROVIDER_HOSTS[provider]
                    or parts.username is not None or parts.password is not None
                    or parts.port is not None):
                raise ValueError("SOURCE_URL_PROVIDER_MISMATCH")
            captured = parse_utc(obs.get("captured_utc"))
            updated = parse_utc(obs.get("source_updated_utc"))
            if captured <= sealed:
                raise ValueError("OBSERVATION_BEFORE_IDENTITY_SEAL")
            if not timedelta(0) <= now - captured <= MAX_AGE:
                raise ValueError("STALE_OR_FUTURE_CAPTURE")
            if (not timedelta(0) <= captured - updated <= MAX_AGE
                    or not timedelta(0) <= now - updated <= MAX_AGE):
                raise ValueError("STALE_OR_FUTURE_SOURCE_UPDATE")
            status = obs.get("match_status")
            if status not in ALL_STATUSES:
                raise ValueError("INVALID_STATUS")
            if (status in LIVE_STATUSES or status == "FINISHED") and now <= ko:
                raise ValueError("MATCH_NOT_STARTED")
            if status == "FINISHED" and now < ko + timedelta(minutes=90):
                raise ValueError("IMPOSSIBLE_EARLY_FINAL")
            if status == "NOT_STARTED" and now >= ko + timedelta(minutes=10):
                raise ValueError("STALE_PREMATCH_STATUS")
            home, away = obs.get("score_home"), obs.get("score_away")
            if (type(home) is not int or type(away) is not int
                    or not 0 <= home <= 30 or not 0 <= away <= 30):
                raise ValueError("INVALID_SCORE")
            if status == "NOT_STARTED" and (home or away):
                raise ValueError("PREMATCH_WITH_GOALS")
            by_provider[provider] = (status, home, away)
        observed = set(by_provider.values())
        if len(observed) != 1:
            raise ValueError("CROSS_SOURCE_SCORE_OR_STATUS_CONFLICT")
        status, home, away = next(iter(observed))
        return {
            "status": "RESEARCH_ONLY",
            "reason": "TWO_PROVIDER_ASSERTIONS_CONSISTENT_NOT_AUTHENTICATED",
            "match_status": status, "score_home": home, "score_away": away,
            "providers": sorted(by_provider),
            "production_recommendations": "DISABLED", "model_scoring_eligible": False,
            "independently_authenticated": False, "settlement_certified": False,
            "price_or_positive_ev_certified": False,
        }
    except (TypeError, ValueError, OverflowError, AttributeError) as error:
        return {**hold, "reason": str(error)}
