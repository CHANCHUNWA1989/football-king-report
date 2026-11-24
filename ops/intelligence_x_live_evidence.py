"""Bounded offline live-score corroboration; not source authentication."""
import re
from live_source_freshness import _parse

FIELDS = frozenset(("source", "fixture_id", "provider_fixture_id", "phase",
                    "home_score", "away_score", "home_red_cards", "away_red_cards",
                    "updated_at", "observed_at", "payload_sha256"))
STATE = ("phase", "home_score", "away_score", "home_red_cards", "away_red_cards")
PHASES = frozenset(("FIRST_HALF", "HALF_TIME", "SECOND_HALF"))
MAX_ROWS = 8


def _id(value):
    return (type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", value)
            is not None and value.upper() not in {"UNKNOWN", "UNVERIFIED", "NONE"})


def _utc(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
        raise ValueError("INVALID_CLOCK")
    parsed = _parse(value)
    if parsed is None:
        raise ValueError("INVALID_CLOCK")
    return parsed


def audit_live(snapshots, *, fixture_id, registry, now_utc):
    """Compare explicit regulation-time score and on-pitch dismissal counts.

    Registry is a caller-provisioned fixture mapping and claimed origin grouping,
    not evidence of independence or rights. Upstream update times and hashes are
    supplied metadata; raw bytes and official card identities are not authenticated.
    Policy: 120s maximum age, 60s maximum pairwise skew. No network or scoring.
    """
    now = _utc(now_utc)
    if not _id(fixture_id) or type(snapshots) is not list or len(snapshots) > MAX_ROWS:
        raise ValueError("INVALID_BATCH")
    if type(registry) is not dict or not 1 <= len(registry) <= MAX_ROWS:
        raise ValueError("INVALID_REGISTRY")
    fields = {"publisher_group", "origin_group", "provider_fixture_id"}
    for source, cfg in registry.items():
        if (not _id(source) or type(cfg) is not dict or cfg.keys() != fields
                or not all(_id(value) for value in cfg.values())):
            raise ValueError("INVALID_REGISTRY")
    reasons, seen, good = set(), set(), []
    for row in snapshots:
        if type(row) is not dict or row.keys() != FIELDS:
            reasons.add("INVALID_FIELDS")
            continue
        source = row["source"]
        if not _id(source) or source not in registry:
            reasons.add("UNKNOWN_SOURCE")
            continue
        if source in seen:
            reasons.add("DUPLICATE_SOURCE")
        seen.add(source)
        cfg = registry[source]
        if (row["fixture_id"] != fixture_id or
                row["provider_fixture_id"] != cfg["provider_fixture_id"]):
            reasons.add("FIXTURE_MISMATCH")
            continue
        if (type(row["phase"]) is not str or row["phase"] not in PHASES or
                any(type(row[k]) is not int or not 0 <= row[k] <= (11 if k.endswith("red_cards") else 99)
                    for k in STATE[1:])):
            reasons.add("INVALID_MATCH_STATE")
            continue
        digest = row["payload_sha256"]
        if type(digest) is not str or not re.fullmatch("[0-9a-f]{64}", digest):
            reasons.add("INVALID_DIGEST")
            continue
        try:
            updated, observed = _utc(row["updated_at"]), _utc(row["observed_at"])
        except (ValueError, OverflowError):
            reasons.add("INVALID_CLOCK")
            continue
        if not updated <= observed <= now or (now - updated).total_seconds() > 120:
            reasons.add("STALE_OR_FUTURE")
            continue
        good.append((cfg["publisher_group"], cfg["origin_group"], digest,
                     updated, observed, tuple(row[k] for k in STATE)))
    if len(good) < 2:
        reasons.add("INSUFFICIENT_SOURCES")
    for i, a in enumerate(good):
        for b in good[i+1:]:
            if a[0] == b[0] or a[1] == b[1]:
                reasons.add("SHARED_ORIGIN_OR_PUBLISHER")
            if a[2] == b[2]:
                reasons.add("DUPLICATE_PAYLOAD")
            if max(abs((a[3]-b[3]).total_seconds()), abs((a[4]-b[4]).total_seconds())) > 60:
                reasons.add("TIME_SKEW")
            if a[5] != b[5]:
                reasons.add("CONFLICTING_MATCH_STATE")
    candidate = not reasons
    return {"schema": "intelligence-x-live-agreement-v1",
            "fixture_id": fixture_id, "source_count": len(seen),
            "diagnostic": "AGREEMENT_CANDIDATE" if candidate else "BLOCKED",
            "match_state": dict(zip(STATE, good[0][5])) if candidate else None,
            "reasons": sorted(reasons | {"SOURCE_RIGHTS_UNVERIFIED", "ORIGIN_UNATTESTED",
                                         "RAW_PAYLOAD_UNVERIFIED", "OFFICIAL_CARD_IDENTITY_UNVERIFIED"}),
            "status": "HOLD", "source_authorized": False, "independently_verified": False,
            "eligible_for_model_scoring": False, "production_recommendations": "DISABLED",
            "external_calls": 0}
