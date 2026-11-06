"""Offline-first real provider sandbox acceptance interface.

Requires explicit allowlisted HTTPS endpoint, environment credential and
archive. Does not claim any live provider was contacted.
"""
from prematch_api_client import fetch_provider_quote
from prematch_integrity_report import evidence_integrity_report


def run_sandbox_acceptance(*, url, api_key_env, fixture, model_version,
                           model_probabilities, evaluated_at_utc, provider_id,
                           archive_directory, allowed_hosts,
                           transport=None, sleeper=None):
    if not isinstance(allowed_hosts, (tuple, list, set)) or not allowed_hosts:
        return {"status": "HOLD", "reason": "SANDBOX_ALLOWLIST_MISSING",
                "production_recommendations": "DISABLED"}
    result = fetch_provider_quote(
        url=url, api_key_env=api_key_env, fixture=fixture,
        model_version=model_version, model_probabilities=model_probabilities,
        evaluated_at_utc=evaluated_at_utc, provider_id=provider_id,
        archive_directory=archive_directory, allowed_hosts=allowed_hosts,
        transport=transport, sleeper=sleeper)
    if result.get("status") != "RESEARCH_ONLY":
        return {**result, "production_recommendations": "DISABLED"}
    integrity = evidence_integrity_report(archive_directory)
    if not integrity["chain_verified"] or integrity["rejection_reasons"]:
        return {"status": "HOLD", "reason": "SANDBOX_EVIDENCE_INVALID",
                "integrity": integrity, "production_recommendations": "DISABLED"}
    return {**result, "sandbox_acceptance": "REPLAYABLE_UNATTESTED",
            "integrity": integrity, "production_recommendations": "DISABLED"}
