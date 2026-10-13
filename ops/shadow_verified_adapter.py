"""Adapt two-source verified FT observations to the paired shadow evaluator.

This adapter never upgrades legacy single-source settlements. It uses the
independent consensus gate, and fails closed on disagreement or missing data.
"""
from datetime import datetime, timezone
from urllib.parse import urlsplit
from result_consensus_gate import verify_result

LABELS = ("home", "draw", "away")
# Approved provenance mapping; caller-supplied group labels are not trusted.
TRUSTED_GROUPS = {"OpenLigaDB": "openligadb", "OpenFootball": "openfootball"}
TRUSTED_HOSTS = {"OpenLigaDB": {"api.openligadb.de"}, "OpenFootball": {"raw.githubusercontent.com"}}

def trusted_origin(provider, url):
    if not isinstance(url, str):
        return False
    try:
        parsed=urlsplit(url)
        return (parsed.scheme=="https" and parsed.hostname in TRUSTED_HOSTS.get(provider,set())
                and parsed.username is None and parsed.password is None
                and parsed.port in (None,443))
    except ValueError:
        return False

def verified_record(sealed, observations):
    """Return a verified audit record or None; no fallback to unverified FT."""
    if not isinstance(sealed, dict):
        return None
    try:
        fixture_id = sealed["fixture_id"]
        kickoff = sealed["kickoff_utc"]
        # Only explicitly allowlisted distinct publishers can establish a
        # two-origin result. Unknown or forged group labels fail closed.
        safe_observations = []
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            provider = obs.get("provider_id")
            if provider not in TRUSTED_GROUPS or obs.get("independent_group_id") != TRUSTED_GROUPS[provider]:
                continue
            # A publisher label alone is not evidence that the collector
            # obtained this score from that publisher. Require a stable
            # upstream fixture URL and raw payload digest for auditability.
            source_url = obs.get("source_url")
            raw_sha256 = obs.get("raw_sha256")
            if (not isinstance(source_url, str)
                    or not trusted_origin(provider, source_url)
                    or not isinstance(raw_sha256, str)
                    or len(raw_sha256) != 64
                    or any(ch not in "0123456789abcdef" for ch in raw_sha256)):
                continue
            safe_observations.append(obs)
        verdict = verify_result(fixture_id, kickoff, safe_observations)
        if verdict["status"] != "VERIFIED":
            return None
        home, away = verdict["result"]
        sources = verdict["source_ids"]
        if len(sources) < 2:
            return None
        # Timestamp of verification cannot be earlier than both published
        # observations. The latest matching source publication is the
        # conservative point at which the agreement could have existed.
        published = []
        for obs in safe_observations:
            if (isinstance(obs, dict) and obs.get("fixture_id") == fixture_id
                    and obs.get("provider_id") in sources
                    and obs.get("status") == "FT"):
                dt = datetime.fromisoformat(obs["published_utc"].replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    return None
                published.append(dt.astimezone(timezone.utc))
        if len(published) < 2:
            return None
        result = "home" if home > away else "away" if home < away else "draw"
        return {
            "fixture_id": fixture_id,
            "kickoff_utc": kickoff,
            "sealed_at_utc": sealed["sealed_at_utc"],
            "market_snapshot_utc": sealed["market_snapshot_utc"],
            "model": sealed["model"],
            "market": sealed["market"],
            "result_verified_at_utc": max(published).isoformat(),
            "result_verified": True,
            "independent_result_sources": sources,
            "result": result,
        }
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return None
