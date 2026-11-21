"""Research-only fail-closed triage for two URL aliases of ONE publisher.

Do not treat matching pages on the same origin as two independent providers.
Never select the "newer" score using scrape time or self-asserted timestamps.
This module has no web retrieval and cannot certify actual game status.
"""
import re
from datetime import timedelta
from urllib.parse import urlparse

from jleague_japanese_status_gate import MAX_AGE, _timestamp


def triage_aliases(observations, *, fixture_id, publisher, host, as_of_utc):
    hold = {
        "status": "HOLD",
        "reason": "INVALID_INPUT",
        "production_recommendations": "DISABLED",
        "independently_authenticated": False,
        "model_scoring_eligible": False,
        "settlement_certified": False,
        "positive_ev_certified": False,
        "can_count_as_two_sources": False,
    }
    try:
        # J1 Kyoto club adapter is deliberately pinned: supplied alias
        # metadata is not evidence of publisher identity by itself.
        if (type(fixture_id) is not str
                or re.fullmatch(r"[0-9]{10}", fixture_id) is None
                or publisher != "kyoto_sanga_official"
                or host != "www.sanga-fc.jp"):
            raise ValueError("MISSING_EXPECTED_IDENTITY")
        expected_urls = {
            f"https://{host}/game/data/{fixture_id}",
            f"https://{host}/index.php/game/data/{fixture_id}",
        }
        if type(observations) is not list or len(observations) != 2:
            raise ValueError("NEED_EXACTLY_TWO_ALIAS_VIEWS")
        now = _timestamp(as_of_utc)
        signatures = []
        urls = set()
        for row in observations:
            if type(row) is not dict:
                raise ValueError("BAD_ALIAS_OBSERVATION")
            if row.get("publisher") != publisher:
                raise ValueError("NOT_SAME_EXPECTED_PUBLISHER")
            if row.get("fixture_id") != fixture_id:
                raise ValueError("FIXTURE_IDENTITY_CONFLICT")
            url = row.get("source_url")
            if type(url) is not str:
                raise ValueError("INVALID_ALIAS_URL")
            parts = urlparse(url)
            if (parts.scheme != "https" or parts.hostname != host
                    or parts.username is not None or parts.password is not None
                    or parts.port is not None or parts.fragment or parts.query
                    or not parts.path.startswith("/")):
                raise ValueError("INVALID_ALIAS_URL")
            # Same-host unrelated pages or another fixture must never
            # become aliases merely because their supplied fixture_id agrees.
            if url not in expected_urls:
                raise ValueError("ALIAS_URL_NOT_BOUND_TO_FIXTURE")
            if url in urls:
                raise ValueError("DUPLICATE_URL_NOT_ALIASES")
            urls.add(url)
            captured = _timestamp(row.get("captured_utc"))
            updated = _timestamp(row.get("source_updated_utc"))
            if (not timedelta(0) <= now - captured <= MAX_AGE
                    or not timedelta(0) <= captured - updated <= MAX_AGE
                    or not timedelta(0) <= now - updated <= MAX_AGE):
                raise ValueError("STALE_OR_FUTURE_ALIAS")
            status = row.get("raw_status")
            home, away = row.get("home_goals"), row.get("away_goals")
            if (type(status) is not str or not status or len(status) > 64
                    or type(home) is not int or type(away) is not int
                    or not (0 <= home <= 30 and 0 <= away <= 30)):
                raise ValueError("INVALID_ALIAS_CONTENT")
            signatures.append((status, home, away))
        if signatures[0] != signatures[1]:
            return {**hold, "reason": "SAME_PUBLISHER_ALIAS_CONFLICT"}
        # Two alias pages never count as a second independent source.
        return {**hold, "reason": "SAME_PUBLISHER_NOT_INDEPENDENT"}
    except (ValueError, TypeError, OverflowError) as exc:
        return {**hold, "reason": str(exc)}
