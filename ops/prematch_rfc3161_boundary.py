"""RFC3161 integration boundary: verify a DER token using pinned TSA roots.

The OpenSSL command validates CMS signature, imprint and TSA certificate
chain. The trust roots must be independently provisioned, never fabricated.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile


def verify_rfc3161_token(raw, token_der, *, tsa_ca_pem=None, openssl="openssl"):
    hold = {"status": "HOLD", "timestamp_verified": False,
            "production_recommendations": "DISABLED"}
    if (not isinstance(raw, bytes) or not raw or len(raw) > 1_000_000
            or not isinstance(token_der, bytes) or not token_der
            or len(token_der) > 100_000):
        return {**hold, "reason": "INVALID_TIMESTAMP_INPUT"}
    if not isinstance(tsa_ca_pem, bytes) or b"BEGIN CERTIFICATE" not in tsa_ca_pem:
        return {**hold, "reason": "TSA_TRUST_ROOT_NOT_CONFIGURED"}
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload.bin").write_bytes(raw)
            (root / "token.tsr").write_bytes(token_der)
            (root / "tsa-ca.pem").write_bytes(tsa_ca_pem)
            result = subprocess.run([
                openssl, "ts", "-verify", "-in", str(root / "token.tsr"),
                "-token_in", "-data", str(root / "payload.bin"),
                "-CAfile", str(root / "tsa-ca.pem")],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
                check=False)
            if result.returncode != 0:
                return {**hold, "reason": "RFC3161_VERIFICATION_FAILED"}
    except (OSError, subprocess.TimeoutExpired):
        return {**hold, "reason": "RFC3161_VERIFIER_UNAVAILABLE"}
    # Cryptographic verification succeeded using the supplied CA file,
    # but independent provisioning of that CA is not established here.
    return {"status": "RESEARCH_ONLY", "timestamp_verified": True,
            "tsa_independently_trusted": False,
            "response_sha256": hashlib.sha256(raw).hexdigest(),
            "production_recommendations": "DISABLED"}
