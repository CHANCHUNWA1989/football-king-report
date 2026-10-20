"""Preserve prospective provider identity claims without authenticating them.

Only the exact OpenLigaDB namespace has a typed interpretation. Sealed rows
are validated, never backfilled from names, dates, or a later source lookup.
"""
import re


OPENLIGA_EVENT_ID = re.compile(r"openligadb:([1-9][0-9]*)\Z")
MATCH_ID = re.compile(r"[1-9][0-9]*\Z")
IDENTITY_FIELDS = ("forecast_event_id", "source_fixture_identity",
                   "source_fixture_identity_status")
SAFETY_FIELDS = ("independently_verified", "eligible_for_model_scoring")


def _event_id(value):
    if (type(value) is not str or not value or len(value) > 512
            or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("INVALID_FORECAST_EVENT_ID")
    return value


def metadata_from_event_id(value):
    """Copy an original forecast ID; only canonical provider IDs gain a type."""
    value = _event_id(value)
    metadata = {"forecast_event_id": value,
                "independently_verified": False, "eligible_for_model_scoring": False}
    match = OPENLIGA_EVENT_ID.fullmatch(value)
    if match:
        metadata.update(source_fixture_identity={"provider": "OpenLigaDB", "match_id": match[1]},
                        source_fixture_identity_status="UNAUTHENTICATED")
    return metadata


def validate_sealed_identity(row):
    """Accept legacy absence; reject malformed, conflicting or promoted claims."""
    if not isinstance(row, dict):
        raise ValueError("INVALID_SEALED_IDENTITY_ROW")
    if not any(field in row for field in IDENTITY_FIELDS):
        return True
    event_id = _event_id(row.get("forecast_event_id"))
    for field in SAFETY_FIELDS:
        if field in row and row[field] is not False:
            raise ValueError("UNSAFE_SOURCE_FIXTURE_IDENTITY")
    if "source_fixture_identity" not in row:
        if "source_fixture_identity_status" in row:
            raise ValueError("SOURCE_FIXTURE_STATUS_WITHOUT_IDENTITY")
        return True
    identity = row["source_fixture_identity"]
    if (type(identity) is not dict or set(identity) != {"provider", "match_id"}
            or type(identity.get("provider")) is not str or identity["provider"] != "OpenLigaDB"
            or type(identity.get("match_id")) is not str
            or not MATCH_ID.fullmatch(identity["match_id"])):
        raise ValueError("INVALID_SOURCE_FIXTURE_IDENTITY")
    expected = OPENLIGA_EVENT_ID.fullmatch(event_id)
    if expected is None or expected[1] != identity["match_id"]:
        raise ValueError("CONFLICTING_SOURCE_FIXTURE_IDENTITY")
    if (row.get("source_fixture_identity_status") != "UNAUTHENTICATED"
            or any(row.get(field) is not False for field in SAFETY_FIELDS)):
        raise ValueError("UNSAFE_SOURCE_FIXTURE_IDENTITY")
    return True


def identity_metadata(row):
    """Export existing metadata with explicit limits, without deriving an ID."""
    validate_sealed_identity(row)
    if not any(field in row for field in IDENTITY_FIELDS):
        return {}
    metadata = {field: row[field] for field in IDENTITY_FIELDS if field in row}
    if "source_fixture_identity" in metadata:
        metadata["source_fixture_identity"] = dict(metadata["source_fixture_identity"])
    metadata.update(independently_verified=False, eligible_for_model_scoring=False)
    return metadata
