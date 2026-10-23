"""Offline quality summary for research-only live-feed admission decisions.

No odds predictions, credentials, API calls, or production betting outputs.
"""
from collections import Counter


def summarize_admissions(decisions):
    if not isinstance(decisions, list):
        return {"status": "HOLD", "reason": "INVALID_DECISION_BATCH",
                "production_recommendations": "DISABLED"}
    statuses = Counter()
    reasons = Counter()
    for item in decisions:
        if not isinstance(item, dict):
            return {"status": "HOLD", "reason": "INVALID_DECISION_ITEM",
                    "production_recommendations": "DISABLED"}
        status = item.get("status")
        reason = item.get("reason")
        if status not in ("HOLD", "RESEARCH_ONLY") or not isinstance(reason, str) or not reason:
            return {"status": "HOLD", "reason": "INVALID_DECISION_ITEM",
                    "production_recommendations": "DISABLED"}
        if item.get("production_recommendations") != "DISABLED":
            return {"status": "HOLD", "reason": "UNSAFE_PRODUCTION_FLAG",
                    "production_recommendations": "DISABLED"}
        statuses[status] += 1
        reasons[reason] += 1
    total = len(decisions)
    return {
        "status": "RESEARCH_ONLY" if total else "HOLD",
        "reason": "OFFLINE_QUALITY_SUMMARY" if total else "NO_OBSERVATIONS",
        "total": total,
        "accepted_research": statuses["RESEARCH_ONLY"],
        "held": statuses["HOLD"],
        "research_acceptance_rate": round(statuses["RESEARCH_ONLY"] / total, 4) if total else None,
        "hold_reasons": dict(sorted((reason, count) for reason, count in reasons.items()
                                    if reason != "SYNCHRONIZED_RESEARCH")),
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False,
    }
