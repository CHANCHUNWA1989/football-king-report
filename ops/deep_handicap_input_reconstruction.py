"""Reconstruct a private DHE candidate from pinned original derived inputs.

The supplied pins and clocks are not independently witnessed. The shadow and
quote-report JSON files are derived inputs, not original provider responses.
This sidecar neither signs nor stores files, contacts sources, or changes an
archived forecast. No raw quote values are returned.
"""
import hashlib
import hmac
from deep_handicap_historical_inputs import _decode
from deep_handicap_private_capture import capture, _digest, _time
from deep_handicap_replay_bridge import bridge, _hash

SCHEMA="football-king-dhe-input-reconstruction-v1"
LIMITS={"shadow":12_000_000,"quote_report":12_000_000,"candidate_report":100_000}


def reconstruct(shadow_raw,quote_raw,candidate_raw,*,pins,expected_capture_utc):
    """Compare all candidate report fields against the registered formula."""
    out={"schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
         "research_only":True,"private_output_only":True,
         "input_byte_pins_matched":False,"formula_reconstruction_matched":False,
         "source_authenticated":False,"external_witness_verified":False,
         "actual_kickoff_authenticated":False,"true_forward_sample_count":0,
         "qualifies_for_betting":False,"positive_expected_value_verified":False,
         "candidate_sha256":None}
    try:
        if type(pins) is not dict or set(pins)!=set(LIMITS):
            raise ValueError("MISSING_EXACT_INPUT_PINS")
        inputs={"shadow":shadow_raw,"quote_report":quote_raw,"candidate_report":candidate_raw}
        for name,raw in inputs.items():
            if type(raw) is not bytes or not 0<len(raw)<=LIMITS[name]:
                raise ValueError("INVALID_INPUT_BYTES")
            pin=pins[name]
            if not _hash(pin) or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin):
                raise ValueError("INPUT_PIN_MISMATCH")
        out["input_byte_pins_matched"]=True
        shadow,quote,stored=(_decode(inputs[k],LIMITS[k]) for k in LIMITS)
        if not all(type(v) is dict for v in (shadow,quote,stored)):
            raise ValueError("INVALID_INPUT_DOCUMENT")
        clock=_time(expected_capture_utc)
        expected=capture(shadow,quote,now=clock)
        if expected.get("candidate") is None:
            raise ValueError("SOURCE_RECONSTRUCTION_GATE_REJECTED")
        # Full canonical equality, not selected fields or permissive numeric
        # equality; bool/int aliases and added fields are rejected.
        if not hmac.compare_digest(_digest(stored),_digest(expected)):
            raise ValueError("CANDIDATE_FORMULA_MISMATCH")
        out.update(formula_reconstruction_matched=True,
                   candidate_sha256=expected["candidate_sha256"],
                   reason="PINNED_DERIVED_INPUT_RECONSTRUCTION_ONLY")
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError,RecursionError) as exc:
        allowed={"MISSING_EXACT_INPUT_PINS","INVALID_INPUT_BYTES","INPUT_PIN_MISMATCH",
                 "INVALID_INPUT_DOCUMENT","SOURCE_RECONSTRUCTION_GATE_REJECTED",
                 "CANDIDATE_FORMULA_MISMATCH"}
        out["reason"]=str(exc) if str(exc) in allowed else "INPUT_RECONSTRUCTION_REJECTED"
    return out


def replay(shadow_raw,quote_raw,candidate_raw,mapping,observations,*,pins,
           expected_capture_utc,as_of_utc,data_kind):
    """Optional stricter private path; no independently authenticated evidence."""
    report=reconstruct(shadow_raw,quote_raw,candidate_raw,pins=pins,
                       expected_capture_utc=expected_capture_utc)
    report["evaluation_row"]=None
    if not report["formula_reconstruction_matched"]:
        return report
    # Inputs are immutable bytes, already bounded and decoded successfully.
    stored=_decode(candidate_raw,LIMITS["candidate_report"])
    result=bridge(stored,mapping,observations,
                  expected_candidate_sha256=report["candidate_sha256"],
                  as_of_utc=as_of_utc,data_kind=data_kind)
    if result["evaluation_row"] is None:
        report["reason"]="RESULT_BRIDGE_REJECTED"
        return report
    report.update(reason="RECONSTRUCTED_STRUCTURAL_REPLAY_ONLY",
                  evaluation_row=result["evaluation_row"])
    return report
