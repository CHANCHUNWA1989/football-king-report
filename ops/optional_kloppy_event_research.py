"""Optional local-only Kloppy EventDataset read adapter for research.

No upstream package is imported, no file/network is read, no predictive
features are approved, and caller-supplied source/license claims are NEVER
treated as independent provenance. This accepts an already-parsed EventDataset
whose public fields match kloppy 3.19.1's documented API.
"""
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

SCHEMA = "football-king-kloppy-local-events-v1"
OUTPUT_SCHEMA = "football-king-kloppy-event-research-v1"
MAX_EVENTS = 20000
_ALLOWED_FIELDS = {
    "schema", "source_namespace", "source_event_id", "rights_reference_url",
    "source_available_utc", "target_as_of_utc",
}


def _id(raw, *, namespace=False):
    if (type(raw) is not str or not 1 <= len(raw) <= 128
            or raw != raw.strip() or any(ord(c) < 33 or ord(c) == 127 for c in raw)):
        raise ValueError("INVALID_SOURCE_ID")
    if namespace and not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", raw):
        raise ValueError("INVALID_SOURCE_NAMESPACE")
    return raw


def _utc(value):
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise ValueError("INVALID_EVENT_AVAILABILITY_TIME")
    try:
        time = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if time.tzinfo is None or time.utcoffset() is None:
            raise ValueError("INVALID_EVENT_AVAILABILITY_TIME")
        return time.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("INVALID_EVENT_AVAILABILITY_TIME") from None


def _rights_url(url):
    if type(url) is not str or len(url) > 300:
        raise ValueError("RIGHTS_REFERENCE_REQUIRED")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("RIGHTS_REFERENCE_REQUIRED")
    return url


def summarize_local_event_dataset(dataset, manifest):
    """Summarize already-loaded historical Kloppy events; no model predictions.

    The manifest is a caller assertion, not a signed proof of rights, file
    contents, observation time, or independence. Never use as a certified
    forward sample, team-strength training set or live betting evidence.
    """
    if (type(manifest) is not dict or set(manifest) != _ALLOWED_FIELDS
            or manifest["schema"] != SCHEMA):
        raise ValueError("INVALID_KLOPPY_MANIFEST")
    namespace = _id(manifest["source_namespace"], namespace=True)
    match_id = _id(manifest["source_event_id"])
    rights = _rights_url(manifest["rights_reference_url"])
    available = _utc(manifest["source_available_utc"])
    as_of = _utc(manifest["target_as_of_utc"])
    if not available < as_of:
        raise ValueError("POST_CUTOFF_OR_UNAVAILABLE_EVENTS")

    metadata = getattr(dataset, "metadata", None)
    if metadata is None or getattr(metadata, "game_id", None) != match_id:
        raise ValueError("MISMATCHED_NATIVE_MATCH_ID")
    teams = getattr(metadata, "teams", None)
    if type(teams) not in (tuple, list) or len(teams) != 2:
        raise ValueError("TWO_NATIVE_TEAMS_REQUIRED")
    ids = tuple(_id(getattr(team, "team_id", None)) for team in teams)
    if ids[0] == ids[1]:
        raise ValueError("DUPLICATE_NATIVE_TEAM_ID")
    events = getattr(dataset, "events", None)
    if events is None or isinstance(events, (str, bytes)) or not hasattr(events, "__iter__"):
        raise ValueError("EVENTS_NOT_ITERABLE")

    seen = {}
    split_ids = set()
    counts = {team: {"pass": 0, "shot": 0} for team in ids}
    total = 0
    for event in events:
        total += 1
        if total > MAX_EVENTS:
            raise ValueError("EVENT_LIMIT_EXCEEDED")
        # A native Kloppy Dataset binds each record back to its exact
        # parent via DataRecord.set_refs(). IDs and team labels are
        # insufficient: mixing a record from another match contaminates
        # descriptive counts without changing the apparent match metadata.
        parent = getattr(event, "dataset", None)
        if parent is None:
            raise ValueError("MISSING_NATIVE_EVENT_DATASET")
        if parent is not dataset:
            raise ValueError("FOREIGN_EVENT_DATASET")
        key = _id(getattr(event, "event_id", None))
        # Kloppy has a *typed* EventType enum. A GenericEvent may expose
        # event_name="shot" from raw provider text and is NOT a ShotEvent.
        # Never promote event_name alone into a typed event category.
        category = getattr(getattr(event, "event_type", None), "name", None)
        if type(category) is not str:
            raise ValueError("MISSING_NATIVE_EVENT_TYPE")
        name = getattr(event, "event_name", None)
        if type(name) is not str:
            raise ValueError("INVALID_EVENT_KIND")

        if key in seen:
            original = seen[key]
            original_type = getattr(getattr(original, "event_type", None), "name", None)
            original_name = getattr(original, "event_name", None)
            original_team = getattr(getattr(original, "team", None), "team_id", None)
            current_team = getattr(getattr(event, "team", None), "team_id", None)
            original_raw = getattr(original, "raw_event", None)
            # StatsBomb Kloppy can produce two *distinct* native records from
            # ONE foul with a card: FOUL_COMMITTED and CARD share a provider
            # event ID and the *same underlying raw event object*. This is
            # the only known valid native duplication, and cannot include a
            # pass, shot, another record, another team or another time.
            valid_split = (
                key not in split_ids
                and {original_type, category} == {"FOUL_COMMITTED", "CARD"}
                and type(original_name) is str
                and original_name.upper() == original_type
                and name.upper() == category
                and original_raw is not None
                and original_raw is getattr(event, "raw_event", None)
                and type(original_team) is str and original_team in counts
                and current_team == original_team
                and getattr(original, "period", None) is not None
                and original.period == getattr(event, "period", None)
                and getattr(original, "timestamp", None) is not None
                and original.timestamp == getattr(event, "timestamp", None)
            )
            if not valid_split:
                raise ValueError("DUPLICATE_NATIVE_EVENT_ID")
            split_ids.add(key)
        else:
            seen[key] = event

        if category not in ("PASS", "SHOT"):
            continue  # Generic/unmapped type: no classified pass/shot.
        if name.upper() != category:
            raise ValueError("INCONSISTENT_NATIVE_EVENT_CLASSIFICATION")
        team = getattr(event, "team", None)
        team_id = getattr(team, "team_id", None)
        if type(team_id) is not str or team_id not in counts:
            raise ValueError("UNKNOWN_EVENT_TEAM")
        counts[team_id][category.lower()] += 1
    if total == 0:
        raise ValueError("NO_EVENTS")

    return {
        "schema": OUTPUT_SCHEMA,
        "status": "RESEARCH_ONLY",
        "source_namespace": namespace,
        "source_event_id": match_id,
        "rights_reference_url": rights,
        "source_available_utc_claimed": manifest["source_available_utc"],
        "target_as_of_utc": manifest["target_as_of_utc"],
        "events_recorded": total,
        "team_event_counts": counts,
        "source_data_rights_independently_verified": False,
        "source_event_capture_independently_verified": False,
        "native_match_identity_independently_verified": False,
        "kickoff_time_verified": False,
        "results_independently_verified": False,
        "pre_match_features_approved": False,
        "model_calibrated": False,
        "positive_ev_verified": False,
        "model_promoted": False,
        "automatic_bets": False,
        "production_recommendations": "DISABLED",
        "warning": "Descriptive event counts only; self-asserted rights/time; not a forecast.",
    }
