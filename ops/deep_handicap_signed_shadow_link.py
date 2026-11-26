"""Link a DHE reconstruction to freshly verified signed shadow input.

The existing forecast verifier checks the three signed forecast subjects
and trusted Rekor time. It does not sign the DHE candidate or quote report.
Never accept saved audit JSON as a witness, or award forward credit.
"""
import hashlib
import hmac
from datetime import datetime,timedelta,timezone
from pathlib import Path

import forecast_provenance_audit as provenance
from deep_handicap_input_reconstruction import reconstruct,LIMITS
from deep_handicap_historical_inputs import _decode
from deep_handicap_private_capture import _time

SCHEMA="football-king-dhe-signed-shadow-link-v1"


def audit(proof,quote_raw,candidate_raw,*,pins,expected_capture_utc,
          source_sha,workflow_sha,run_id,attempt,now=None):
    out={"schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
         "research_only":True,"private_output_only":True,
         "shadow_signature_verified":False,"shadow_subject_bytes_matched":False,
         "shadow_witness_before_candidate_cutoff":False,
         "candidate_formula_reconstruction_matched":False,
         "candidate_independent_witness_verified":False,
         "quote_independent_witness_verified":False,
         "actual_kickoff_authenticated":False,"source_authenticated":False,
         "true_forward_sample_count":0,"qualifies_for_betting":False,
         "positive_expected_value_verified":False}
    try:
        current=now if now is not None else datetime.now(timezone.utc)
        if (not isinstance(current,datetime) or current.tzinfo is None
                or current.utcoffset() is None or not isinstance(proof,Path)
                or ".." in proof.parts
                or any(p.is_symlink() for p in (proof.absolute(),*proof.absolute().parents))):
            raise ValueError("INVALID_PROOF_CONTEXT")
        current=current.astimezone(timezone.utc)
        cutoff=_time(expected_capture_utc)
        if cutoff>current:
            raise ValueError("FUTURE_CANDIDATE_CUTOFF")
        # Invoke the actual existing verifier, with its fixed repository,
        # workflow, branch, signer, run/attempt and three-subject policy.
        # There is no argument accepting a saved verification report.
        verified=provenance.audit(proof,source_sha=source_sha,workflow_sha=workflow_sha,
                                  run_id=run_id,attempt=attempt,now=current)
        if not (verified.get("audit_completed") is True
                and verified.get("signature_identity_and_subjects_verified") is True):
            raise ValueError("SHADOW_ATTESTATION_NOT_VERIFIED")
        out["shadow_signature_verified"]=True
        raw=provenance._read(proof/"shadow.json",provenance.MAX_FILE_BYTES)
        digest=hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(digest,verified["subject_sha256"]["shadow.json"]):
            raise ValueError("SIGNED_SHADOW_BYTES_CHANGED")
        out["shadow_subject_bytes_matched"]=True
        witness=provenance._time(verified["verified_tlog_utc"],utc_only=True)
        if not witness<=cutoff<=current:
            raise ValueError("SHADOW_WITNESS_AFTER_CANDIDATE_CUTOFF")
        out["shadow_witness_before_candidate_cutoff"]=True
        result=reconstruct(raw,quote_raw,candidate_raw,pins=pins,expected_capture_utc=expected_capture_utc)
        if result.get("formula_reconstruction_matched") is not True:
            raise ValueError("DHE_FORMULA_RECONSTRUCTION_REJECTED")
        candidate=_decode(candidate_raw,LIMITS["candidate_report"])["candidate"]
        ko=_time(candidate["kickoff_utc"])
        if not witness<=cutoff<ko-timedelta(minutes=10):
            raise ValueError("RECORDED_KICKOFF_BUFFER_REJECTED")
        out.update(candidate_formula_reconstruction_matched=True,
                   signed_shadow_sha256=digest,
                   candidate_sha256=result["candidate_sha256"],
                   verified_shadow_tlog_utc=witness.isoformat(),
                   reason="SIGNED_SHADOW_LINK_ONLY_CANDIDATE_UNWITNESSED")
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError) as exc:
        allowed={"INVALID_PROOF_CONTEXT","FUTURE_CANDIDATE_CUTOFF",
                 "SHADOW_ATTESTATION_NOT_VERIFIED","SIGNED_SHADOW_BYTES_CHANGED",
                 "SHADOW_WITNESS_AFTER_CANDIDATE_CUTOFF",
                 "DHE_FORMULA_RECONSTRUCTION_REJECTED","RECORDED_KICKOFF_BUFFER_REJECTED"}
        out["reason"]=str(exc) if str(exc) in allowed else "SIGNED_SHADOW_LINK_REJECTED"
    return out
