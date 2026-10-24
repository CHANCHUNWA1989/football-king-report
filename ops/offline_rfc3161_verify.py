"""Optional OpenSSL RFC3161 token verification with independently pinned TSA trust.

OpenSSL verifies CMS signature, signer chain, message imprint and timestamp
token semantics. This does not establish independent pre-match capture.
"""
import hashlib
import re
import subprocess
from pathlib import Path


def verify_rfc3161_token(*, token_path, evidence_path, ca_bundle_path,
                         expected_ca_bundle_sha256, expected_token_sha256=None, openssl="openssl"):
    hold = {"status": "HOLD", "reason": "RFC3161_CRYPTOGRAPHIC_VERIFICATION_FAILED",
            "rfc3161_signature_verified": False,
            "tsa_certificate_chain_verified": False,
            "rfc3161_message_imprint_verified": False,
            "trusted_timestamp_authority_verified": False,
            "tsa_operator_identity_verified": False,
            "prematch_capture_independence_verified": False,
            "production_recommendations": "DISABLED"}
    if (not isinstance(expected_ca_bundle_sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_ca_bundle_sha256) is None
            or not isinstance(expected_token_sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_token_sha256) is None
            or openssl != "openssl"):
        return hold
    try:
        token = Path(token_path)
        evidence = Path(evidence_path)
        ca_bundle = Path(ca_bundle_path)
        if (not token.is_file() or not evidence.is_file() or not ca_bundle.is_file()
                or token.stat().st_size > 65_536
                or evidence.stat().st_size > 100_000
                or ca_bundle.stat().st_size > 100_000):
            return hold
        if hashlib.sha256(token.read_bytes()).hexdigest() != expected_token_sha256.lower():
            return hold
        if hashlib.sha256(ca_bundle.read_bytes()).hexdigest() != expected_ca_bundle_sha256.lower():
            return hold
        result = subprocess.run(
            ["openssl", "ts", "-verify", "-token_in", "-in", str(token),
             "-data", str(evidence), "-CAfile", str(ca_bundle)],
            capture_output=True, timeout=10, check=False)
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return hold
    if result.returncode != 0 or result.stdout.strip() != b"Verification: OK":
        return hold
    return {"status": "RESEARCH_ONLY", "reason": "RFC3161_OPENSSL_VERIFIED",
            "rfc3161_signature_verified": True,
            "trusted_timestamp_authority_verified": False,
            "tsa_certificate_chain_verified": True,
            "rfc3161_message_imprint_verified": True,
            "tsa_operator_identity_verified": False,
            "prematch_capture_independence_verified": False,
            "production_recommendations": "DISABLED"}
