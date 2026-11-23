"""Deny-only, zero-network source-rights preflight for untrusted metadata.

This module is NOT a legal approval engine or a provider authenticator.
Caller-supplied rights digests, hostnames and timestamps are all unauthenticated.
Even a structurally complete dossier MUST remain HOLD and require independent
legal/source/provenance assessment before any source is connected to production.
No raw contracts, secrets, responses, URLs, odds, or model output enter here.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

SCHEMA = "football-king-inplay-source-rights-preflight-v1"
FIXTURE_ID = re.compile(r"[A-Za-z0-9_.:-]{1,120}\Z")
PROVIDER = re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
DOMAIN_TLD = re.compile(r"[a-z]{2,63}\Z")
DOSSIER_KEYS = {
    "schema", "fixture_id_claim", "decision_utc_claim",
    "private_inventory_sha256_unattested", "sources",
}
SOURCE_KEYS = {
    "provider_claim", "api_host_claim", "rights_record_sha256_unattested",
    "capture_receipt_sha256_unattested", "rights_expiry_utc_claim",
    "requested_uses_claim",
}
USES = frozenset({
    "internal_research", "inplay_analytics", "model_training",
    "odds_analytics", "redistribution", "betting_recommendations",
})
RESERVED_SUFFIXES = frozenset({"localhost", "local", "internal", "invalid", "test"})


def _hold(reason="INVALID_UNTRUSTED_SOURCE_PREFLIGHT"):
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": reason,
        "ready_for_independent_review": False,
        "candidate_source_count": 0,
        "preflight_sha256_unattested": None,
        "source_authorized": False,
        "source_data_access_enabled": False,
        "provider_identity_authenticated": False,
        "source_independence_verified": False,
        "third_party_timestamp_verified": False,
        "original_provider_response_authenticated": False,
        "durable_storage_independently_verified": False,
        "eligible_for_model_input": False,
        "eligible_for_model_scoring": False,
        "positive_ev_verified": False,
        "certified_forward_samples": 0,
        "production_recommendations": "DISABLED",
        "recommendation": None,
        "roi": None,
    }


def _require(ok):
    if not ok:
        raise ValueError("INVALID_UNTRUSTED_SOURCE_PREFLIGHT")


def _digest(value):
    return type(value) is str and DIGEST.fullmatch(value) is not None


def _stamp(value):
    _require(type(value) is str and 1 <= len(value) <= 64)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0))
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("INVALID_UNTRUSTED_SOURCE_PREFLIGHT") from None


def _host(value):
    if type(value) is not str or not 4 <= len(value) <= 253:
        return False
    parts = value.split(".")
    if len(parts) < 2 or parts[-1] in RESERVED_SUFFIXES:
        return False
    return (all(LABEL.fullmatch(part) is not None for part in parts[:-1])
            and DOMAIN_TLD.fullmatch(parts[-1]) is not None
            and parts[0] != "localhost"
            and not value.startswith("localhost."))


def _now(value):
    current = datetime.now(timezone.utc) if value is None else value
    _require(type(current) is datetime and current.tzinfo is not None
             and current.utcoffset() is not None)
    return current.astimezone(timezone.utc)


def assess_source_readiness(dossier, *, now=None):
    """Validate shape only, NEVER grant real-world license or live-data admission.

    A positive readiness flag says only that the unverified metadata is shaped
    well enough to place in an external legal/provenance review queue.
    """
    try:
        current = _now(now)
        _require(type(dossier) is dict and set(dossier) == DOSSIER_KEYS)
        _require(dossier["schema"] == SCHEMA)
        _require(type(dossier["fixture_id_claim"]) is str
                 and FIXTURE_ID.fullmatch(dossier["fixture_id_claim"]) is not None)
        _require(_digest(dossier["private_inventory_sha256_unattested"]))
        decision = _stamp(dossier["decision_utc_claim"])
        _require(decision <= current)
        sources = dossier["sources"]
        _require(type(sources) is list and len(sources) == 2)
        providers, hosts, receipts = set(), set(), set()
        for source in sources:
            _require(type(source) is dict and set(source) == SOURCE_KEYS)
            name, host = source["provider_claim"], source["api_host_claim"]
            _require(type(name) is str and PROVIDER.fullmatch(name) is not None)
            _require(_host(host))
            _require(name not in providers and host not in hosts)
            providers.add(name)
            hosts.add(host)
            for key in ("rights_record_sha256_unattested",
                        "capture_receipt_sha256_unattested"):
                _require(_digest(source[key]))
            receipt = source["capture_receipt_sha256_unattested"]
            _require(receipt not in receipts)
            receipts.add(receipt)
            _require(_stamp(source["rights_expiry_utc_claim"]) > current)
            requested = source["requested_uses_claim"]
            _require(type(requested) is list and 1 <= len(requested) <= len(USES))
            _require(all(type(x) is str and x in USES for x in requested))
            _require(len(set(requested)) == len(requested))
        canonical = {
            **{k: v for k, v in dossier.items() if k != "sources"},
            "sources": sorted(
                ({**src, "requested_uses_claim": sorted(src["requested_uses_claim"])}
                 for src in sources),
                key=lambda src: src["provider_claim"]),
        }
        data = json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
        return {
            **_hold("EXTERNAL_LICENSE_AND_PROVENANCE_REVIEW_REQUIRED"),
            "ready_for_independent_review": True,
            "candidate_source_count": 2,
            "preflight_sha256_unattested": hashlib.sha256(data).hexdigest(),
        }
    except (ValueError, TypeError, OverflowError, KeyError, AttributeError,
            RecursionError):
        return _hold()
