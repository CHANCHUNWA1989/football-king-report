"""Offline typed news agreement diagnostics, never proof of independent origin."""
import re
from intelligence_x_firecrawl_candidate import _clock, _url

VALUES = {"injury": {"OUT", "DOUBTFUL", "AVAILABLE"},
          "lineup": {"STARTER", "BENCH", "NOT_IN_SQUAD"},
          "red_card": {"CONFIRMED", "RESCINDED"},
          "club_notice": {"ISSUED", "WITHDRAWN"}}
MAX_ROWS = 100


def _id(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", value):
        raise ValueError("INVALID_ID")
    return value


def _digest(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("INVALID_DIGEST")
    return value


def compare(rows, *, registry, fixture_id, subject_id, claim_id, kind, now_utc):
    """Registry is caller-reviewed configuration, not authenticated rights or origin.
    Claim identity/values are pre-normalized externally, never extracted here.
    One batch must describe exactly one fixture, subject, claim and type.
    """
    key = tuple(_id(x) for x in (fixture_id, subject_id, claim_id, kind))
    if kind not in VALUES or type(rows) is not list or len(rows) > MAX_ROWS:
        raise ValueError("INVALID_BATCH")
    if type(registry) is not dict or not 1 <= len(registry) <= MAX_ROWS:
        raise ValueError("INVALID_REGISTRY")
    cfg = {}
    for url, identity in registry.items():
        _url(url)
        if type(identity) is not dict:
            raise ValueError("INVALID_REGISTRY")
        cfg[url] = (_id(identity.get("publisher_group")), _id(identity.get("origin_group")))
    now = _clock(now_utc)
    seen = set()
    pairs = []
    reasons = set()
    for row in rows:
        if type(row) is not dict or tuple(row.get(k) for k in
                ("fixture_id", "subject_id", "claim_id", "kind")) != key:
            raise ValueError("CLAIM_IDENTITY_MISMATCH")
        url = _url(row.get("source_url"))
        if url not in cfg:
            raise ValueError("UNKNOWN_SOURCE")
        if url in seen:
            reasons.add("DUPLICATE_SOURCE")
        seen.add(url)
        if type(row.get("value")) is not str or row["value"] not in VALUES[kind]:
            raise ValueError("INVALID_CLAIM_VALUE")
        payload = _digest(row.get("payload_sha256"))
        # Exact normalized excerpt digest supplied by extractor; not an originality proof.
        excerpt = _digest(row.get("excerpt_sha256"))
        collected = _clock(row.get("collected_at"))
        observed_raw = row.get("upstream_observed_at")
        if observed_raw is None:
            reasons.add("UPSTREAM_CLOCK_MISSING")
        else:
            observed = _clock(observed_raw)
            if observed > collected or not 0 <= (now - observed).total_seconds() <= 900:
                reasons.add("UPSTREAM_CLOCK_OUT_OF_RANGE")
        if not 0 <= (now - collected).total_seconds() <= 900:
            reasons.add("COLLECTION_CLOCK_OUT_OF_RANGE")
        pairs.append((url, *cfg[url], payload, excerpt, row["value"]))
    if len(pairs) < 2:
        reasons.add("INSUFFICIENT_SOURCES")
    for i, a in enumerate(pairs):
        for b in pairs[i + 1:]:
            if a[1] == b[1]:
                reasons.add("SHARED_PUBLISHER_GROUP")
            if a[2] == b[2]:
                reasons.add("SHARED_ORIGIN_GROUP")
            if a[3] == b[3]:
                reasons.add("DUPLICATE_PAYLOAD")
            if a[4] == b[4]:
                reasons.add("DUPLICATE_EXCERPT")
            if a[5] != b[5]:
                reasons.add("CONFLICTING_CLAIMS")
    candidate = not reasons
    return {"schema": "intelligence-x-claim-agreement-v1",
            "fixture_id": fixture_id, "subject_id": subject_id,
            "claim_id": claim_id, "kind": kind, "source_count": len(seen),
            "diagnostic": "AGREEMENT_CANDIDATE" if candidate else "BLOCKED",
            "reasons": sorted(reasons | {"ORIGIN_INDEPENDENCE_UNATTESTED",
                                       "SOURCE_RIGHTS_UNVERIFIED",
                                       "CLAIM_EXTRACTION_UNVERIFIED"}),
            "status": "HOLD", "independently_verified": False,
            "source_authorized": False, "eligible_for_model_scoring": False,
            "production_recommendations": "DISABLED"}
