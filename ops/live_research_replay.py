"""Offline end-to-end research admission replay.

Registry pin must be provided by trusted caller, not by provider payload.
No external API access, live trading, EV calculation, or production output.
"""
from live_local_registry_entry import admit_from_local_registry
from live_quality_report import summarize_admissions


def replay_live_research(samples, *, registry_path=None, expected_sha256=None, now=None):
    if not isinstance(samples, list) or len(samples) > 10000:
        return {"status": "HOLD", "reason": "INVALID_REPLAY_BATCH",
                "production_recommendations": "DISABLED", "quality": None}
    decisions = []
    for sample in samples:
        result = admit_from_local_registry(
            sample, registry_path=registry_path,
            expected_sha256=expected_sha256, now=now)
        decisions.append({
            "status": result["status"],
            "reason": result["reason"],
            "production_recommendations": "DISABLED",
        })
    quality = summarize_admissions(decisions)
    return {"status": quality["status"], "reason": "OFFLINE_REPLAY",
            "production_recommendations": "DISABLED",
            "quality": quality, "sample_count": len(samples)}
