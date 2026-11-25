"""Historical market timestamp coverage audit, never a quote or trading signal.

The legacy settlement archive contains derived 1X2 consensus and timestamps,
not raw bookmaker prices or opening/closing histories. No source authentication,
probability fitting, execution or promotion. All timestamps are claims.
"""
from datetime import datetime
import math
from statistics import median

MAX_ROWS = 10000


def _stamp(value):
    if type(value) is not str or not value or len(value) > 48:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        raise ValueError("INVALID_TIMESTAMP") from None
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return t


def audit_market_timing(archive):
    if type(archive) is not dict or archive.get("schema") != "football-king-forward-research-1":
        raise ValueError("INVALID_ARCHIVE_SCHEMA")
    rows = archive.get("samples")
    if type(rows) is not list or len(rows) > MAX_ROWS:
        raise ValueError("INVALID_ARCHIVE_ROWS")
    if type(archive.get("n")) is not int or archive["n"] != len(rows):
        raise ValueError("ARCHIVE_COUNT_MISMATCH")
    gaps, leads, forecast_leads = [], [], []
    seen = set()
    after_forecast = 0
    for row in rows:
        if type(row) is not dict or type(row.get("key")) is not str or not row["key"].strip() or row["key"] in seen:
            raise ValueError("DUPLICATE_OR_INVALID_FIXTURE_KEY")
        seen.add(row["key"])
        kickoff, forecast, market = (_stamp(row.get(k)) for k in
                                     ("kickoff_utc", "forecast_utc", "market_utc"))
        if not forecast < kickoff or not market < kickoff:
            raise ValueError("POST_KICKOFF_TIMESTAMP")
        gap = (forecast-market).total_seconds()
        after_forecast += int(gap < 0)
        gaps.append(gap)
        leads.append((kickoff-market).total_seconds())
        forecast_leads.append((kickoff-forecast).total_seconds())

    def describe(values):
        return ({k: v/60 for k, v in
                 (("min", min(values)), ("median", median(values)), ("max", max(values)))}
                if values else None)

    # Later market timestamps are counted separately, never admitted to
    # a same-as-of comparison even when close to a model's forecast time.
    return {
        "status": "HOLD", "production_recommendations": "DISABLED",
        "archive_rows": len(rows), "timestamp_claims_authenticated": False,
        "market_after_forecast": after_forecast,
        "market_to_forecast_gap_minutes": describe(gaps),
        "market_to_kickoff_lead_minutes": describe(leads),
        "forecast_to_kickoff_lead_minutes": describe(forecast_leads),
        "prior_market_within_minutes": {str(m): sum(0 <= g <= 60*m for g in gaps)
                                        for m in (2, 5, 20)},
        "prematch_market_within_kickoff_minutes": {str(m): sum(0 < g <= 60*m for g in leads)
                                                  for m in (2, 5, 10, 60)},
        "opening_price_evidence_available": False,
        "closing_price_evidence_available": False,
        "raw_bookmaker_overround_available": False,
        "actual_asian_market_history_available": False,
        "independent_same_time_comparison_certified": False,
        "certified_prospective_samples": 0,
    }
