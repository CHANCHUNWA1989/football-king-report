"""Bounded offline batch summary for Intelligence-X; no network or publication."""
from intelligence_x_firecrawl_v2_response import normalize_response
from intelligence_x_firecrawl_candidate import _clock, MAX_BYTES

MAX_BATCH = 32
MAX_BATCH_BYTES = 4 * 1024 * 1024


def summarize(captures, *, reviewed_urls, now_utc):
    _clock(now_utc)
    if type(captures) is not list or len(captures) > MAX_BATCH:
        raise ValueError("INVALID_BATCH")
    if any(type(row) is not dict for row in captures):
        raise ValueError("INVALID_BATCH_ROW")
    if sum(len(row["raw"]) for row in captures
           if type(row.get("raw")) is bytes) > MAX_BATCH_BYTES:
        raise ValueError("BATCH_BYTES_EXCEEDED")
    accepted = rejected = 0
    seen = set()
    for row in captures:
        try:
            candidate = normalize_response(
                row.get("raw"), requested_url=row.get("requested_url"),
                reviewed_urls=reviewed_urls, collected_at=row.get("collected_at"),
                now_utc=now_utc, http_status=row.get("http_status"))
            identity = (candidate["source_url"], candidate["payload_sha256"])
            if identity in seen:
                raise ValueError("DUPLICATE_CAPTURE")
            seen.add(identity)
            accepted += 1
        except (ValueError, TypeError, OverflowError):
            rejected += 1
    return {"schema": "intelligence-x-offline-batch-v1",
            "total": len(captures), "candidates": accepted, "rejected": rejected,
            "status": "HOLD", "source_authorized": False,
            "independently_verified": False, "eligible_for_model_scoring": False,
            "production_recommendations": "DISABLED",
            "external_calls": 0, "corroboration_executed": False}
