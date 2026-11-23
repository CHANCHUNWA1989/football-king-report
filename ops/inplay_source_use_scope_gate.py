"""Offline claimed rights scope reconciliation: ALWAYS deny live source admission.

Grant metadata is caller-supplied and unverified. The objective is to catch
obvious mismatches in use, territory, holder, time or claimed revocation before
external legal review. It is NOT an independent rights registry, cryptographic
signature verifier, license, authenticated publisher response, provider API,
or betting/model permission. There is intentionally no release path.
"""
from datetime import datetime
import hashlib
import json
import re

from inplay_source_rights_preflight import (
    USES, _digest, _now, _stamp, assess_source_readiness,
)

SCHEMA = "football-king-inplay-source-use-scope-gate-v1"
GRANT_KEYS = frozenset({
    "provider_claim", "license_holder_claim", "rights_record_sha256_unattested",
    "covered_uses_claim", "denied_uses_claim", "territories_claim",
    "valid_from_utc_claim", "valid_until_utc_claim", "revocation_status_claim",
})
HOLDER = re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
TERRITORY = re.compile(r"[A-Z]{2}\Z")
MAX_TERRITORIES = 16


def _hold(reason="INVALID_OR_UNTRUSTED_RIGHTS_SCOPE_CLAIMS"):
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": reason,
        "ready_for_external_rights_review": False,
        "candidate_grant_count": 0,
        "scope_matrix_sha256_unattested": None,
        "source_authorized": False,
        "source_data_access_enabled": False,
        "provider_identity_authenticated": False,
        "signed_grant_verified": False,
        "revocation_registry_independently_verified": False,
        "independent_license_holder_verified": False,
        "source_independence_verified": False,
        "third_party_timestamp_verified": False,
        "eligible_for_model_input": False,
        "eligible_for_model_scoring": False,
        "positive_ev_verified": False,
        "certified_forward_samples": 0,
        "production_recommendations": "DISABLED",
        "recommendation": None,
        "roi": None,
    }


def _check(condition):
    if not condition:
        raise ValueError("INVALID_OR_UNTRUSTED_RIGHTS_SCOPE_CLAIMS")


def _uses(items, *, allow_empty):
    _check(type(items) is list and len(items) <= len(USES)
           and (allow_empty or len(items) > 0))
    _check(all(type(x) is str and x in USES for x in items))
    _check(len(set(items)) == len(items))
    return set(items)


def _territories(items):
    _check(type(items) is list and 1 <= len(items) <= MAX_TERRITORIES)
    _check(all(type(x) is str and TERRITORY.fullmatch(x) is not None for x in items))
    _check(len(set(items)) == len(items))
    return set(items)


def audit_scope_claims(dossier, grants, *, requested_use, territory,
                       license_holder, now=None):
    """Structural comparison; a matching claim remains HOLD until verified.

    An external signer/rights owner and independent revocation registry have
    NOT been queried, and a caller can fabricate all claimed metadata.
    Never interpret ready_for_external_rights_review as access authorization.
    """
    try:
        current = _now(now)
        _check(type(requested_use) is str and requested_use in USES)
        _check(type(territory) is str and TERRITORY.fullmatch(territory) is not None)
        _check(type(license_holder) is str
               and HOLDER.fullmatch(license_holder) is not None)
        preflight = assess_source_readiness(dossier, now=current)
        _check(preflight["ready_for_independent_review"] is True)
        _check(type(grants) is list and len(grants) == 2)
        providers = {source["provider_claim"]: source for source in dossier["sources"]}
        _check(len(providers) == 2)
        checked, observed = [], set()
        for claim in grants:
            _check(type(claim) is dict and set(claim) == GRANT_KEYS)
            provider = claim["provider_claim"]
            _check(type(provider) is str and provider in providers
                   and provider not in observed)
            observed.add(provider)
            source = providers[provider]
            _check(claim["license_holder_claim"] == license_holder)
            _check(_digest(claim["rights_record_sha256_unattested"])
                   and claim["rights_record_sha256_unattested"]
                       == source["rights_record_sha256_unattested"])
            allowed = _uses(claim["covered_uses_claim"], allow_empty=False)
            denied = _uses(claim["denied_uses_claim"], allow_empty=True)
            _check(not (allowed & denied))
            _check(requested_use in allowed and requested_use not in denied
                   and requested_use in source["requested_uses_claim"])
            _check(territory in _territories(claim["territories_claim"]))
            starts = _stamp(claim["valid_from_utc_claim"])
            ends = _stamp(claim["valid_until_utc_claim"])
            self_claimed_rights_end = _stamp(source["rights_expiry_utc_claim"])
            _check(starts <= current < ends <= self_claimed_rights_end)
            _check(claim["revocation_status_claim"] == "NO_REVOKE_REPORTED")
            checked.append({
                "provider_claim": provider,
                "license_holder_claim": license_holder,
                "rights_record_sha256_unattested":
                    claim["rights_record_sha256_unattested"],
                "covered_uses_claim": sorted(allowed),
                "denied_uses_claim": sorted(denied),
                "territories_claim": sorted(claim["territories_claim"]),
                "valid_from_utc_claim": starts.isoformat(),
                "valid_until_utc_claim": ends.isoformat(),
                "revocation_status_claim": "NO_REVOKE_REPORTED",
            })
        _check(observed == set(providers))
        packet = {
            "schema": SCHEMA,
            "preflight_sha256_unattested": preflight["preflight_sha256_unattested"],
            "requested_use": requested_use,
            "territory": territory,
            "license_holder_claim": license_holder,
            "grants": sorted(checked, key=lambda row: row["provider_claim"]),
        }
        raw = json.dumps(packet, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
        return {
            **_hold("SCOPE_CLAIMS_MATCH_EXTERNAL_VERIFICATION_STILL_REQUIRED"),
            "ready_for_external_rights_review": True,
            "candidate_grant_count": 2,
            "scope_matrix_sha256_unattested": hashlib.sha256(raw).hexdigest(),
        }
    except (ValueError, KeyError, TypeError, OverflowError,
            AttributeError, RecursionError):
        return _hold()
