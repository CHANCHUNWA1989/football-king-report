"""Optional read-only evidence from the exact normalized gateway response.

Capture before schedule enrichment. Requested competition context is not
publisher-authenticated competition identity. Never infer missing native IDs
or rewrite a legacy archive. No source calls or forecast inputs are added.
"""
import hashlib
import json
from datetime import datetime, timezone
from collections import Counter

LEAGUES = {"epl", "championship", "bundesliga", "laliga", "seriea", "ligue1"}
MAX_ROWS = 1200


def utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIMESTAMP")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return stamp.astimezone(timezone.utc)


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def capture_batch(league, season, raw, observed, *, replay):
    """Retain a bounded projection, including explicit missing values."""
    result = {"requested_league": league, "season": season, "replay": replay,
              "observed_utc": observed.isoformat(), "status": "HOLD",
              "source": raw.get("source"), "source_url": raw.get("source_url"),
              "reported_capture_utc": raw.get("captured_utc"),
              "rows": [], "rejected": {}, "identity_authenticated": False}
    rows = raw.get("matches")
    if (league not in LEAGUES or raw.get("status") != "READY_RESEARCH"
            or raw.get("league") not in (None, league)
            or not isinstance(rows, list) or len(rows) > MAX_ROWS):
        result["reason"] = "INVALID_OR_OVERSIZE_BATCH"
        return result
    result["input_row_count"] = len(rows)
    result["gateway_reported_league"] = raw.get("league")
    counts = Counter()
    try:
        source_at = utc(raw.get("captured_utc"))
        if source_at > observed:
            raise ValueError("FUTURE_CAPTURE")
        if not (isinstance(raw.get("source"), str) and raw["source"].strip()
                and isinstance(raw.get("source_url"), str)
                and raw["source_url"].startswith("https://")):
            raise ValueError("MISSING_SOURCE")
        result["source_context_complete"] = True
    except (ValueError, TypeError, OverflowError):
        result["source_context_complete"] = False
    for row in rows:
        if not isinstance(row, dict):
            counts["INVALID_ROW"] += 1
            continue
        if row.get("league") not in (None, league):
            counts["ROW_COMPETITION_CONFLICT"] += 1
            continue
        projection = {k: row.get(k) for k in
                      ("league", "event_id", "date", "home", "away",
                       "kickoff_utc", "status")}
        # Native input is retained only if the existing gateway supplied it.
        # No score or derived fixture is added to this optional evidence.
        result["rows"].append(projection)
    result["rejected"] = dict(counts)
    result["projection_sha256"] = digest(result["rows"])
    result["status"] = "RESEARCH_ONLY" if result["source_context_complete"] else "HOLD"
    return result


def assemble(batches, completed, *, clock_problem=None):
    return {"schema": "football-king-gateway-source-evidence-v1",
            "completed_utc": completed.isoformat(), "batches": batches,
            "batch_count": len(batches), "clock_problem": clock_problem,
            "batches_sha256": digest(batches), "status": "HOLD",
            "competition_identity_authenticated": False,
            "source_identity_authenticated": False,
            "missing_gateway_fixtures_proven": False,
            "admitted_new_fixtures": 0,
            "production_recommendations": "DISABLED"}
