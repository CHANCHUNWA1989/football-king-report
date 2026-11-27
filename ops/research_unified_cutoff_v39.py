"""V39: common-cutoff integrity for a declared prematch research batch.

Caller-supplied fixture identity and clocks are not authenticated. Local integrity
and replay never confer external timestamp, training, or production permission.
"""
from datetime import datetime, timezone
from .research_unified_batch_replay_v38 import reconcile, valid_id, MAX_EVENTS
from .research_unified_prematch_replay_v35 import digest

MAX_QUOTE_AGE_SECONDS = 300
MAX_FORECAST_AGE_SECONDS = 86400

def utc(value):
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise ValueError("invalid timestamp")
    t = datetime.fromisoformat(value)
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("timezone required")
    return t.astimezone(timezone.utc)

def audit_batch(roster, records, *, cutoff, root="."):
    report = {
        "schema": "unified-cutoff-v39", "status": "HOLD",
        "production_recommendations": "DISABLED", "cutoff_verified": False,
        "batch_replay_verified": False, "source_identity_authenticated": False,
        "roster_authenticated": False, "external_timestamp_verified": False,
        "training_admission": False, "qualified_for_production": False,
        "verified_executable_ev": False, "local_batch_sha256": None,
    }
    try:
        asof = utc(cutoff)
        if type(roster) is not dict or not 1 <= len(roster) <= MAX_EVENTS:
            raise ValueError("invalid roster")
        if any(not valid_id(e) for e in roster):
            raise ValueError("invalid fixture ID")
        fixtures = {e: utc(t) for e, t in roster.items()}
        if any(k <= asof for k in fixtures.values()):
            raise ValueError("fixture already started at cutoff")
        batch = reconcile(list(fixtures), records, root=root)
        report["reconciliation"] = batch
        if batch.get("batch_replay_verified") is not True:
            raise ValueError("batch replay rejected")
        report["batch_replay_verified"] = True
        witnesses = []
        for r in records:
            e = r["event_id"]
            if utc(r["kickoff"]) != fixtures[e]:
                raise ValueError("declared kickoff mismatch")
            frozen = utc(r["frozen_at"])
            if not 0 <= (asof-frozen).total_seconds() <= MAX_QUOTE_AGE_SECONDS:
                raise ValueError("snapshot outside common cutoff window")
            for key, clock_key, max_age in (
                ("quotes", "observed_at", MAX_QUOTE_AGE_SECONDS),
                ("forecasts", "observed", MAX_FORECAST_AGE_SECONDS),
            ):
                for item in r[key]:
                    observed = utc(item[clock_key])
                    if observed > frozen or not 0 <= (asof-observed).total_seconds() <= max_age:
                        raise ValueError("evidence stale or future at common cutoff")
            witnesses.append({"event_id":e, "sha256":r["sha256"]})
        manifest = {
            "schema": report["schema"], "cutoff":asof.isoformat(),
            "roster":{e:k.isoformat() for e,k in fixtures.items()},
            "records":sorted(witnesses,key=lambda r:r["event_id"]),
            "quote_max_age_seconds":MAX_QUOTE_AGE_SECONDS,
            "forecast_max_age_seconds":MAX_FORECAST_AGE_SECONDS,
        }
        report.update(cutoff_verified=True, local_batch_sha256=digest(manifest),
                      fixture_count=len(fixtures), cutoff_utc=asof.isoformat())
    except (ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError,
            RecursionError) as exc:
        report["reason"] = str(exc)
    return report
