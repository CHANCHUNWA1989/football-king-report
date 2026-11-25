"""Connect original prematch bytes to two normalized postmatch claims.

Not a raw provider parser or TSA verifier. A digest of a normalized claim
does not authenticate its publisher. Never admit a certified case, emit
scores/prices, or score a model. No I/O or network.
"""
from datetime import timedelta
from hashlib import sha256

from ops.first_case_payload_binding import (
    inspect, _read_json, _time, _name, FORECAST_KEYS, FORECAST_SCHEMA,
)

RESULT_SCHEMA = "football-king-postmatch-normalized-claim-v1"
RESULT_KEYS = frozenset({
    "schema", "fixture_id", "league", "home_key", "away_key",
    "kickoff_utc", "actual_kickoff_utc", "finished_utc", "observed_utc",
    "provider", "upstream_origin", "native_event_id", "score_scope",
    "home_goals", "away_goals", "prematch_manifest_sha256",
    "production_recommendations",
})


def _hold(reason):
    return {"status": "HOLD", "reason": reason,
            "production_recommendations": "DISABLED",
            "certified_forward_case_count": 0, "eligible_for_model_scoring": False,
            "source_origins_independently_verified": False,
            "actual_kickoff_authenticated": False,
            "external_timestamp_verified": False,
            "raw_provider_capture_verified": False,
            "positive_ev_verified": False, "claim_chain_consistent": False}


def audit(forecast_raw, quote_raw, manifest_raw, result_a_raw, result_b_raw, *, as_of_utc):
    try:
        prematch = inspect(forecast_raw, quote_raw, manifest_raw)
        forecast = _read_json(forecast_raw, FORECAST_KEYS, FORECAST_SCHEMA)
        cutoff = _time(as_of_utc)
        kickoff = _time(forecast["kickoff_utc"])
        claims = [_read_json(raw, RESULT_KEYS, RESULT_SCHEMA)
                  for raw in (result_a_raw, result_b_raw)]
        for claim in claims:
            if any(_name(claim[k]) != forecast[k]
                   for k in ("fixture_id", "league", "home_key", "away_key")):
                raise ValueError("RESULT_FIXTURE_MISMATCH")
            if claim["prematch_manifest_sha256"] != prematch["manifest_sha256"]:
                raise ValueError("RESULT_MANIFEST_MISMATCH")
            # Conservative pilot: rescheduling or actual kickoff disagreement
            # needs a separately authenticated reconciliation, never an override.
            if _time(claim["kickoff_utc"]) != kickoff or _time(claim["actual_kickoff_utc"]) != kickoff:
                raise ValueError("KICKOFF_RECONCILIATION_REQUIRED")
            if not (kickoff + timedelta(minutes=90) <= _time(claim["finished_utc"])
                    <= _time(claim["observed_utc"]) <= cutoff):
                raise ValueError("RESULT_TIME_ORDER_INVALID")
            for k in ("provider", "upstream_origin", "native_event_id"):
                _name(claim[k])
            if claim["score_scope"] != "FT90" or any(
                type(claim[k]) is not int or not 0 <= claim[k] <= 20
                for k in ("home_goals", "away_goals")):
                raise ValueError("INVALID_REGULATION_RESULT")
        a, b = claims
        for k in ("provider", "upstream_origin"):
            if a[k].casefold() == b[k].casefold():
                raise ValueError("SHARED_CLAIMED_SOURCE_ORIGIN")
        if any(a[k] != b[k] for k in ("home_goals", "away_goals")):
            raise ValueError("RESULT_SCORE_DISAGREEMENT")
        return {**_hold("NORMALIZED_CLAIMS_MATCH_EXTERNAL_PROOF_REQUIRED"),
                "claim_chain_consistent": True,
                "prematch_manifest_sha256": prematch["manifest_sha256"],
                "normalized_result_claim_sha256": sorted(
                    sha256(raw).hexdigest() for raw in (result_a_raw, result_b_raw))}
    except (ValueError, TypeError, OverflowError, RecursionError):
        # Do not echo untrusted inputs or private metadata on failure.
        return _hold("INVALID_OR_CONFLICTING_CASE_CHAIN")
