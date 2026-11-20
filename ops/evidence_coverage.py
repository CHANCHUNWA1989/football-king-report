"""Offline evidence coverage report. Never certifies source authenticity or positive EV."""
from collections import Counter
from decimal import Decimal
from ops.snapshot_validation import validate_dataset

PRODUCTION_RECOMMENDATIONS = "DISABLED"

def evidence_coverage(records, *, max_quote_age_minutes=30):
    """Fail closed on invalid records and report structural coverage only.

    Source authenticity, licensing, model training lineage, closing odds,
    sample independence and out-of-sample calibration require separate review.
    """
    normalized = validate_dataset(records, max_quote_age_minutes=max_quote_age_minutes)
    competitions = Counter(row["competition"] for row in normalized)
    markets = Counter(row["market"] + ":" + row["side"] for row in normalized)
    providers = Counter(row["bookmaker"] for row in normalized)
    event_ids = set(row["event_id"] for row in normalized)
    return {
        "snapshot_count": len(normalized),
        "unique_event_count": len(event_ids),
        "competitions": dict(sorted(competitions.items())),
        "markets": dict(sorted(markets.items())),
        "bookmakers": dict(sorted(providers.items())),
        "structurally_valid": True,
        "source_authenticity_verified": False,
        "licensing_verified": False,
        "out_of_sample_verified": False,
        "closing_line_value_verified": False,
        "positive_ev_verified": False,
        "production_recommendation_allowed": False,
    }
