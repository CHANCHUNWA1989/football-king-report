"""Reconcile collection diagnostics with retained observations, never certify coverage."""
from datetime import datetime, timedelta, timezone

FIELDS = ("source_scheduled_fixtures", "retained_fixture_observations",
          "fixture_observations_omitted", "catalogue_cards_total",
          "catalogue_cards_examined", "catalogue_cards_omitted_by_bound",
          "eligible_catalogue_leagues", "schedule_only_catalogue_leagues",
          "requested_leagues", "eligible_not_selected", "ambiguous_candidate_entries")
STATUS_SCHEMA = "football-king-worldwide-source-build-status-v1"

def clock(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_CLOCK")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("UNZONED_CLOCK")
    return d.astimezone(timezone.utc)

def reconcile(status, worldwide, now):
    out = {"status": "HOLD", "production_recommendations": "DISABLED",
           "global_coverage_complete": False, "counts": None,
           "reason": "SOURCE_DIAGNOSTICS_UNAVAILABLE_OR_UNSAFE"}
    if (not isinstance(status, dict) or status.get("schema") != STATUS_SCHEMA
            or status.get("production_recommendations") != "DISABLED"
            or not isinstance(worldwide, dict)
            or worldwide.get("production_recommendations") != "DISABLED"):
        return out
    try:
        stamp = clock(status["collected_utc"])
        if stamp != clock(worldwide["collected_utc"]) or not now-timedelta(hours=10) <= stamp <= now:
            raise ValueError("CLOCK_MISMATCH_OR_STALE")
        counts = {k:status[k] for k in FIELDS}
        if any(type(v) is not int or v < 0 for v in counts.values()):
            raise ValueError("INVALID_COUNT")
        batches = worldwide["leagues"]
        if not isinstance(batches, list) or any(not isinstance(x, dict)
                or not isinstance(x.get("fixture_observations"), list) for x in batches):
            raise ValueError("INVALID_BATCH")
        actual = sum(len(x["fixture_observations"]) for x in batches)
        if (counts["retained_fixture_observations"] != actual
                or counts["source_scheduled_fixtures"] != actual+counts["fixture_observations_omitted"]
                or counts["catalogue_cards_total"] != counts["catalogue_cards_examined"]+counts["catalogue_cards_omitted_by_bound"]
                or counts["eligible_catalogue_leagues"]+counts["schedule_only_catalogue_leagues"] != counts["requested_leagues"]+counts["eligible_not_selected"]
                or counts["requested_leagues"] > 12 or counts["catalogue_cards_examined"] > 400
                or counts["eligible_catalogue_leagues"]+counts["schedule_only_catalogue_leagues"]+counts["ambiguous_candidate_entries"] > counts["catalogue_cards_examined"]):
            raise ValueError("ACCOUNTING_MISMATCH")
    except (KeyError, ValueError, TypeError, OverflowError):
        out["reason"] = "SOURCE_DIAGNOSTICS_NOT_RECONCILED"
        return out
    out.update(counts=counts, reason="LOCAL_COUNTS_RECONCILED_NOT_GLOBAL_COVERAGE")
    return out
