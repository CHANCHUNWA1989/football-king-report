"""PR-07 source-rights admission and per-fixture evidence linkage.

No user-provided policy, source_group, URL or 'licensed=true' flag can grant
access to unknown-rights or unknown-upstream sources. A witnessed forecast can
be linked to later source observations but NEVER becomes a certified score,
OOS sample, market quote or approved bet by that association.
"""
from datetime import timedelta

from ops.trusted_result_evidence import _policy
from vnext_forecast_attestation_gate import audit_witness
from vnext_prospective_local_seal import (
    audit_source_independence, read_forecast_seal,
)
from vnext_shadow_forward_audit import _clock, _id, _sha

SCHEMA = "football-king-vnext-per-fixture-evidence-link-v1"
OPERATIONS = frozenset({
    "AUTOMATED_COLLECTION", "DERIVED_METADATA", "PUBLIC_RAW_REUSE",
})
MATCH_FIELDS = frozenset({
    "fixture_id", "kickoff_utc", "home_goals", "away_goals",
    "result_received_utc", "source_raw_sha256",
    "result_independently_authenticated",
})


def _hold(reason, **extra):
    return {
        "schema": SCHEMA, "status": "HOLD",
        "reason": reason if type(reason) is str and len(reason) < 128
                  else "FIXTURE_EVIDENCE_REJECTED",
        "source_access_authorized": False,
        "publisher_independence_authenticated": False,
        "result_truth_verified": False, "actual_kickoff_verified": False,
        "eligible_for_model_scoring": False,
        "eligible_for_betting": False, "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
        **extra,
    }


def audit_source_access(provider, *, scope, operation):
    """Read only the existing SHA-pinned restrictive policy, fail closed."""
    try:
        policy = _policy()
        if type(provider) is not str or provider not in policy["providers"]:
            raise ValueError("SOURCE_NOT_IN_PINNED_POLICY")
        if scope != policy["scope"] or operation not in OPERATIONS:
            raise ValueError("SOURCE_OPERATION_OR_SCOPE_NOT_AUTHORIZED")
        rules = policy["providers"][provider]
        if rules["upstream_relationship"] != "UNKNOWN":
            # Policy should never be silently broadened by this PR.
            raise ValueError("UNEXPECTED_PINNED_POLICY_RELATIONSHIP")
        if rules["public_raw_reuse"] not in (
                "NOT_ESTABLISHED", "REQUIRES_SCOPE_SPECIFIC_LICENSE_REVIEW"):
            raise ValueError("UNEXPECTED_PINNED_RIGHTS_ASSERTION")
        reason = ("DFB_AUTOMATED_COLLECTION_AND_PUBLIC_RAW_REUSE_NOT_AUTHORIZED"
                  if provider == "DFB" and operation in (
                      "AUTOMATED_COLLECTION", "PUBLIC_RAW_REUSE")
                  else "SCOPE_SPECIFIC_RIGHTS_AND_UPSTREAM_INDEPENDENCE_UNVERIFIED")
        return _hold(
            reason, provider=provider, operation=operation, scope=scope,
            policy_id=policy["policy_id"],
            source_rights_scope=rules["public_raw_reuse"],
            upstream_relationship=rules["upstream_relationship"],
        )
    except (ValueError, TypeError, KeyError, OSError) as exc:
        return _hold(str(exc) or "INVALID_SOURCE_POLICY")


def link_fixture(root, file_name, *, expected_sha256, bundle_path,
                 source_commit, workflow_commit, run_id, attempt,
                 result_record, result_observations, checked_utc=None):
    """Link by *exact canonical fixture ID*, not team name or fuzzy kickoff.

    A verified GitHub forecast witness is a byte/time proof only. Unknown
    source rights/upstream and the absence of independent result attestation
    keep the overall outcome HOLD. No synthetic data can be promoted.
    """
    try:
        proof = audit_witness(
            root, file_name, expected_sha256=expected_sha256,
            bundle_path=bundle_path, source_commit=source_commit,
            workflow_commit=workflow_commit, run_id=run_id, attempt=attempt,
            checked_utc=checked_utc)
        if proof["status"] != "WITNESSED_BYTES_RESEARCH":
            raise ValueError("FORECAST_WITNESS_NOT_AUTHENTICATED")
        seal = read_forecast_seal(root, file_name, expected_sha256=expected_sha256)
        pair = seal["pair"]
        fid = pair["fixture_id"]
        if (type(result_record) is not dict or
                set(result_record) != MATCH_FIELDS):
            raise ValueError("INVALID_RESULT_JOIN_SCHEMA")
        if (result_record["fixture_id"] != fid or
                _clock(result_record["kickoff_utc"]) != _clock(pair["kickoff_utc"]) or
                not _sha(result_record["source_raw_sha256"]) or
                result_record["result_independently_authenticated"] is not False):
            raise ValueError("RESULT_IDENTITY_OR_CERTIFICATION_CONFLICT")
        if any(type(result_record[k]) is not int or
               not 0 <= result_record[k] <= 30 for k in ("home_goals", "away_goals")):
            raise ValueError("INVALID_RESULT_SCORE")
        kickoff, result_received = (
            _clock(pair["kickoff_utc"]),
            _clock(result_record["result_received_utc"]),
        )
        if result_received < kickoff + timedelta(minutes=90):
            raise ValueError("RESULT_BEFORE_REGULATION_COMPLETION")
        # A research join must never borrow a result that the verifier itself
        # had not received by its own evaluated UTC timestamp.
        from datetime import datetime, timezone
        evaluation = (_clock(checked_utc) if checked_utc is not None
                      else datetime.now(timezone.utc))
        if result_received > evaluation:
            raise ValueError("RESULT_NOT_AVAILABLE_AT_LINK_TIME")
        observation = audit_source_independence(
            result_observations, fixture_id=fid,
            decision_utc=result_record["result_received_utc"])
        if observation.get("observation_agreement") is not True:
            raise ValueError("RESULT_SOURCES_DISAGREE_OR_OUTSIDE_POLICY")
        if any(item[k] != result_record[k] for item in result_observations
               for k in ("home_goals", "away_goals")):
            raise ValueError("RESULT_NOT_SUPPORTED_BY_OBSERVATIONS")
        # Policy access is checked separately for *each* asserted provider;
        # identical scores never authorize new licensed collection.
        providers = []
        for item in result_observations:
            gate = audit_source_access(
                item["provider"], scope=item["source_scope"],
                operation="DERIVED_METADATA")
            if gate["status"] != "HOLD" or not gate.get("policy_id"):
                raise ValueError("SOURCE_POLICY_MISSING_OR_CHANGED")
            providers.append({
                "provider": item["provider"],
                "provider_fixture_id_unverified": item["provider_fixture_id"],
                "raw_sha256_unverified": item["raw_sha256"],
                "rights_verified": False,
            })
        return _hold(
            "WITNESSED_FORECAST_BUT_RESULT_RIGHTS_AND_INDEPENDENCE_UNVERIFIED",
            fixture_id=fid,
            forecast_sha256=expected_sha256,
            forecast_witness_utc=proof["witness_utc"],
            forecast_external_byte_time_verified=True,
            observation_agreement=True,
            provider_references=sorted(providers, key=lambda item: item["provider"]),
            forecast_source_references=[{
                "provider": row["provider"],
                "source_event_id_unverified": row["source_event_id"],
                "raw_sha256_unverified": row["raw_sha256"],
            } for row in seal["source_refs"]],
            result_raw_sha256_unverified=result_record["source_raw_sha256"],
            actual_kickoff_verified=False,
            result_truth_verified=False,
        )
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as exc:
        return _hold(str(exc) or "PER_FIXTURE_EVIDENCE_LINK_REJECTED")
