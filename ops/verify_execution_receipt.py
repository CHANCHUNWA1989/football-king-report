"""Fail-closed pre-publish binding between true model invocation and site data.

Checks the *original A* event fields after permitted research overlays, not
the whole JSON: AB/DC may legitimately attach separate research-only fields.
A matching digest is not an independent provider or timestamp attestation.
"""
import argparse
import hashlib
import json
from pathlib import Path
from shadow_execution_runner import (
    SCHEMA, _forecast_signature, _native_fixture_fails_closed,
    _native_receipt_sha, _time,
)
import shadow_forecast


def verify(shadow, receipt):
    if (type(shadow) is not dict or type(receipt) is not dict
            or receipt.get("schema") != SCHEMA
            or shadow.get("schema") != "football-king-uncalibrated-shadow-1"
            or shadow.get("production_recommendations") != "DISABLED"
            or receipt.get("production_recommendations") != "DISABLED"):
        raise ValueError("UNSAFE_OR_MISSING_EXECUTION_RECEIPT")
    if (type(shadow.get("predictions")) is not list
            or type(shadow.get("predictions_count")) is not int
            or shadow["predictions_count"] != len(shadow["predictions"])
            or type(receipt.get("valid_original_A_fixture_outputs")) is not int
            or receipt["valid_original_A_fixture_outputs"] != len(shadow["predictions"])):
        raise ValueError("EXECUTION_RECEIPT_COUNT_MISMATCH")
    if (receipt.get("as_of_utc") != shadow.get("as_of_utc")
            or receipt.get("model_execution_observed") is not bool(shadow["predictions"])
            or receipt.get("status") != ("RESEARCH_ONLY" if shadow["predictions"] else "HOLD")
            or receipt.get("verified_positive_ev") is not False
            or receipt.get("model_invocation_externally_attested") is not False
            or receipt.get("source_identity_authenticated") is not False
            or receipt.get("formal_forward_scoring_eligible") is not False):
        raise ValueError("UNSAFE_RECEIPT_STATUS_OR_TIME")
    entered = _time(receipt.get("run_entered_utc"))
    completed = _time(receipt.get("run_completed_utc"))
    asof = _time(receipt.get("as_of_utc"))
    if not entered <= asof <= completed:
        raise ValueError("UNSAFE_RECEIPT_TIME_ORDER")
    actual_model_sha = hashlib.sha256(
        Path(shadow_forecast.__file__).read_bytes()).hexdigest()
    if actual_model_sha != receipt.get("model_code_sha256"):
        raise ValueError("MODEL_CODE_CHANGED_SINCE_INVOCATION")
    invocations = receipt.get("invocation_trace")
    ids = receipt.get("event_ids_unverified")
    if (type(invocations) is not list or type(ids) is not list
            or type(receipt.get("original_A_function_calls")) is not int
            or receipt["original_A_function_calls"] != len(invocations)
            or len(ids) != len(shadow["predictions"])):
        raise ValueError("MISSING_OR_INVALID_EXECUTION_TRACE")
    signatures = {}
    for trace in invocations:
        if (type(trace) is not dict or trace.get("league") not in shadow_forecast.LEAGUES
                or type(trace.get("invoked")) is not bool or trace["invoked"] is not True
                or type(trace.get("success")) is not bool):
            raise ValueError("INVALID_MODEL_INVOCATION_EVENT")
        if trace["success"] is not True:
            continue
        event_ids = trace.get("produced_event_ids_unverified")
        digests = trace.get("output_signatures_sha256")
        if (type(event_ids) is not list or type(digests) is not list
                or len(event_ids) != len(digests)):
            raise ValueError("INVALID_MODEL_INVOCATION_SIGNATURES")
        for event_id, digest in zip(event_ids, digests):
            if (type(event_id) is not str or type(digest) is not str
                    or len(digest) != 64):
                raise ValueError("INVALID_MODEL_INVOCATION_SIGNATURE")
            token = (trace["league"], event_id)
            if token in signatures:
                raise ValueError("DUPLICATE_MODEL_INVOCATION_EVENT")
            signatures[token] = digest
    seen = set()
    for row, label in zip(shadow["predictions"], ids):
        if (type(row) is not dict or type(label) is not dict
                or row.get("production_recommendations") != "DISABLED"
                or row.get("prediction_utc") != shadow["as_of_utc"]):
            raise ValueError("UNSAFE_PUBLISHED_MODEL_EVENT")
        token = (row.get("league"), row.get("event_id"))
        if (token in seen or token not in signatures
                or label != {"league": token[0],
                             "source_event_id_unverified": token[1],
                             "native_fixture_input_sha256_not_source_attestation":
                                 _native_receipt_sha(row)}
                or _forecast_signature(row) != signatures[token]):
            raise ValueError("PUBLISHED_MODEL_EVENT_NOT_OBSERVED")
        if _native_fixture_fails_closed(row):
            raise ValueError("UNSAFE_NATIVE_FIXTURE_PROVENANCE")
        seen.add(token)
    return {
        "status": "VERIFIED_PROCESS_ONLY" if seen else "HOLD",
        "observed_events": len(seen),
        "model_function_called": receipt["original_A_function_calls"] > 0,
        "source_authenticated": False,
        "betting_eligible": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    args=parser.parse_args(argv)
    site=Path(args.site)
    result=verify(
        json.loads((site/"shadow.json").read_text(encoding="utf-8")),
        json.loads((site/"model_execution_receipt.json").read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False))


if __name__=="__main__":
    main()
