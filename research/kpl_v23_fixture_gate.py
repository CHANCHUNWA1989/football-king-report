"""KPL V23: offline source-backed future-fixture research HOLD dossier.

A real upcoming fixture *candidate* is not a registered V20 prospective
trial. This module checks internally asserted source agreement, deadlines
and explicit abstention. It does not fetch web pages, authenticate publisher
identity, authorize data rights, build BP inputs, or produce odds/picks.
No source string or Git commit proves independent official pregame timing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from research.kpl_v11_forecast_archive import _time
from research.kpl_v20_shadow_trial import _id

DOSSIER_KEYS = frozenset({
    "fixture_key", "tournament_id", "format", "teams",
    "scheduled_session_at", "official_fixture_id", "decision",
    "probability_a", "bp_status", "model_status", "rights_status",
    "trial_registration_status", "independent_tsa_status", "observations",
})
OBS_KEYS = frozenset({
    "source_id", "source_url", "role", "published_at",
    "scheduled_session_at", "teams", "independently_authenticated",
})
ROLES = frozenset({
    "OFFICIAL_LEAGUE_SESSION_CLAIM",
    "TEAM_MATCHUP_ANNOUNCEMENT_CLAIM",
    "INDEPENDENT_FIXTURE_LISTING_CLAIM",
})
EXPECTED_ROLES = frozenset(ROLES)
MAX_SOURCE_ITEMS = 12
MAX_DOSSIER_BYTES = 32_768


def _utcnow():
    """This clock is a local process input, NOT independent time evidence."""
    return datetime.now(timezone.utc)


def _hold(reasons, *, key=None, session=None, sources=0, consistent=False):
    return {
        "status": "HOLD",
        "fixture_key": key,
        "scheduled_session_at": session,
        "source_claim_count": sources,
        "technical_schedule_claims_consistent": bool(consistent),
        "decision": "HOLD",
        "probability_a": None,
        "trial_started": False,
        "v20_registration_performed": False,
        "official_fixture_id_authenticated": False,
        "publisher_identity_independently_authenticated": False,
        "independent_source_capture_time_verified": False,
        "first_map_kickoff_time_verified": False,
        "bp_complete_and_authenticated": False,
        "actual_kpl_model_calibration_verified": False,
        "rights_for_real_data_verified": False,
        "tsa_timestamp_independently_witnessed": False,
        "real_kpl_prediction_accuracy_verified": False,
        "positive_ev_verified": False,
        "live_execution_allowed": False,
        "production_recommendations": "DISABLED",
        "research_only": True,
        "reasons": list(dict.fromkeys(reasons)),
    }


def _unique(pairs):
    out = {}
    for key, val in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = val
    return out


def load_fixture_dossier(path):
    """Bounded single-read JSON with exact keys and no duplicate keys/NaN."""
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_DOSSIER_BYTES + 1)
    if not raw or len(raw) > MAX_DOSSIER_BYTES:
        raise ValueError("invalid future fixture dossier size")
    try:
        obj = json.loads(
            raw, object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("invalid future fixture JSON") from exc
    if not isinstance(obj, dict):
        raise ValueError("invalid future fixture object")
    return obj


def _source_host(url):
    if not isinstance(url, str) or not 1 <= len(url) <= 2048:
        raise ValueError("invalid source URL")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname is None
            or parsed.username or parsed.password or parsed.port is not None
            or parsed.fragment or not parsed.path.startswith("/")
            or parsed.hostname.lower() != parsed.hostname):
        raise ValueError("unsafe or unqualified source URL")
    return parsed.hostname


def _valid_teams(value):
    return (isinstance(value, list) and len(value) == 2
            and all(_id(v) for v in value) and value[0] != value[1])


def screen_fixture_dossier(dossier, *, now=None):
    """Check source *claims* for one known future BO7 and insist on HOLD.

    Only tournament-session date/time is corroborated by the league calendar;
    team announcement and independent fixture page provide match identity.
    They are separately asserted, not independently authenticated in code.
    A tournament 18:00 SESSION is never called the exact G1 kickoff.
    """
    if not isinstance(dossier, dict) or set(dossier) != DOSSIER_KEYS:
        return _hold(["INVALID_OR_INCOMPLETE_DOSSIER_SCHEMA"])
    key = dossier.get("fixture_key")
    session = dossier.get("scheduled_session_at")
    if (not _id(key) or not _id(dossier["tournament_id"])
            or dossier["format"] != "BO7"
            or not _valid_teams(dossier["teams"])
            or dossier["official_fixture_id"] is not None
            or dossier["decision"] != "HOLD"
            or dossier["probability_a"] is not None
            or dossier["bp_status"] != "UNVERIFIED"
            or dossier["model_status"] != "UNCALIBRATED"
            or dossier["rights_status"] != "UNVERIFIED"
            or dossier["trial_registration_status"] != "NOT_REGISTERED"
            or dossier["independent_tsa_status"] != "NOT_VERIFIED"):
        return _hold(["PREDICTION_OR_AUTHORITY_PREMATURELY_ASSERTED"], key=key)
    try:
        when = _time(session)
        current = _utcnow() if now is None else _time(now)
    except (TypeError, ValueError, OverflowError):
        return _hold(["INVALID_FIXTURE_TIME"], key=key)
    if when <= current:
        return _hold(["SESSION_ALREADY_STARTED_OR_IN_PAST"], key=key,
                     session=session)
    items = dossier["observations"]
    if not isinstance(items, list) or not 3 <= len(items) <= MAX_SOURCE_ITEMS:
        return _hold(["INSUFFICIENT_DISTINCT_FIXTURE_EVIDENCE"], key=key,
                     session=session)
    sources, roles, matchup_hosts = set(), set(), set()
    for item in items:
        if not isinstance(item, dict) or set(item) != OBS_KEYS:
            return _hold(["INVALID_SOURCE_OBSERVATION_SCHEMA"], key=key,
                         session=session)
        role = item["role"]
        if role not in ROLES or not _id(item["source_id"]):
            return _hold(["UNSUPPORTED_SOURCE_ROLE_OR_ID"], key=key,
                         session=session)
        try:
            host = _source_host(item["source_url"])
            src_time = _time(item["scheduled_session_at"])
            published = (None if item["published_at"] is None
                         else _time(item["published_at"]))
        except (ValueError, TypeError, OverflowError):
            return _hold(["INVALID_SOURCE_URL_OR_CLOCK"], key=key,
                         session=session)
        if (src_time != when or published is not None
                and not published < min(when, current)):
            return _hold(["CONFLICTING_OR_FUTURE_SOURCE_CLAIM"], key=key,
                         session=session)
        # A source claiming itself independent is not accepted as a fact.
        if item["independently_authenticated"] is not False:
            return _hold(["SELF_ASSERTED_INDEPENDENT_AUTHENTICATION"], key=key,
                         session=session)
        if role == "OFFICIAL_LEAGUE_SESSION_CLAIM":
            if item["teams"] is not None:
                return _hold(["SESSION_ONLY_SOURCE_CLAIMS_TEAM_MATCHUP"],
                             key=key, session=session)
        else:
            if (not _valid_teams(item["teams"])
                    or set(item["teams"]) != set(dossier["teams"])):
                return _hold(["CONFLICTING_MATCHUP_IDENTITIES"], key=key,
                             session=session)
            matchup_hosts.add(host)
        identity = (item["source_id"], item["source_url"])
        if identity in sources or item["source_url"] in {x[1] for x in sources}:
            return _hold(["DUPLICATE_FIXTURE_SOURCE"], key=key, session=session)
        sources.add(identity)
        roles.add(role)
    if not EXPECTED_ROLES.issubset(roles) or len(matchup_hosts) < 2:
        return _hold(["MISSING_ROLE_OR_NONINDEPENDENT_MATCHUP_HOSTS"],
                     key=key, session=session, sources=len(sources))
    return _hold([
        "SOURCE_CLAIMS_CONSISTENT_BUT_NOT_AUTHENTICATED",
        "NO_VERIFIED_FIRST_MAP_KICKOFF_BP_OR_CALIBRATED_PROBABILITY",
        "NO_INDEPENDENT_TSA_OR_PRE_REGISTERED_V20_TRIAL",
        "WAIT_FOR_INDEPENDENT_SOURCE_AND_RIGHTS_REVIEW",
    ], key=key, session=session, sources=len(sources), consistent=True)


def screen_fixture_file(path, *, now=None):
    try:
        return screen_fixture_dossier(load_fixture_dossier(path), now=now)
    except (ValueError, TypeError, OSError):
        return _hold(["INVALID_OR_UNREADABLE_FIXTURE_DOSSIER"])


if __name__ == "__main__":
    import sys
    filename = (sys.argv[1] if len(sys.argv) == 2 else
                "research/kpl_v23_20261104_ttg_wolves_fixture.json")
    print(json.dumps(screen_fixture_file(filename), sort_keys=True))
