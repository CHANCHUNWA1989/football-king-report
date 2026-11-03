"""KPL V15: offline RFC3161 timestamp-token and signed-envelope trust gate.

Security scope: verify token imprint/signature/chain for a pinned TSA signer
at token genTime, and a pinned V14 Ed25519 research receipt bound to an
archive. No network calls, no trust root embedded in this code, no claim of
revocation status when unavailable, and NO production/unlock outcome.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from research.kpl_v11_forecast_archive import _time
from research.kpl_v13_archive_snapshot import read_verified_archive_snapshot
from research.kpl_v14_signed_anchor import (
    _inspect_signed, canonical_signed_message,
)

MAX_TOKEN = 128_000
MAX_CERT = 12_000
MAX_CRL = 64_000
HEX64 = re.compile(r"^[0-9a-f]{64}$")
OID = re.compile(r"^[0-9]+(?:\.[0-9]+){2,20}$")
TRUST_KEYS = frozenset({
    "root_ca_pem", "root_cert_sha256", "tsa_cert_pem",
    "tsa_cert_sha256", "allowed_policies",
})


def _hold(reasons, *, signed=False, token=False, chain=False, window=False,
          revocation=False):
    return {
        "status": "HOLD",
        "reasons": list(dict.fromkeys(reasons)),
        "ed25519_pinned_signature_verified": signed,
        "rfc3161_token_signature_and_imprint_verified": token,
        "tsa_certificate_chain_valid_at_gen_time": chain,
        "tsa_timestamp_within_forecast_window": window,
        "revocation_status_locally_checked": revocation,
        "trust_anchor_independently_authenticated": False,
        "tsa_identity_independently_authenticated": False,
        "external_timestamp_fully_trusted": False,
        "provider_data_rights_verified": False,
        "research_only": True,
        "live_execution_allowed": False,
        "production_recommendations": "DISABLED",
    }


def _run(argv, *, data=None):
    """OpenSSL verification with timeout; any backend exception fails closed."""
    try:
        return subprocess.run(
            argv, input=data, capture_output=True, check=False, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("CRYPTO_BACKEND_UNAVAILABLE") from exc


def _pem_cert_der(cert_pem):
    with tempfile.TemporaryDirectory(prefix="kpl15-cert-") as folder:
        cert = Path(folder) / "cert.pem"
        cert.write_bytes(cert_pem.encode("ascii"))
        result = _run(["openssl", "x509", "-in", str(cert), "-outform", "DER"])
        if result.returncode != 0 or not result.stdout:
            raise ValueError("invalid x509 cert")
        return result.stdout


def _pin_trust(trust):
    """Pinned cert bytes must be provided via independent trusted config."""
    if not isinstance(trust, dict) or set(trust) != TRUST_KEYS:
        return "INVALID_TSA_TRUST_CONFIG"
    for name, pin in (("root_ca_pem", "root_cert_sha256"),
                      ("tsa_cert_pem", "tsa_cert_sha256")):
        cert, sha = trust.get(name), trust.get(pin)
        if (not isinstance(cert, str) or len(cert) > MAX_CERT
                or not cert.startswith("-----BEGIN CERTIFICATE-----")
                or not isinstance(sha, str) or HEX64.fullmatch(sha) is None):
            return "INVALID_TSA_TRUST_CONFIG"
        try:
            der = _pem_cert_der(cert)
        except (ValueError, UnicodeError):
            return "INVALID_TSA_CERTIFICATE"
        except RuntimeError:
            return "CRYPTO_BACKEND_UNAVAILABLE"
        if hashlib.sha256(der).hexdigest() != sha:
            return "PINNED_TSA_CERTIFICATE_MISMATCH"
    policies = trust.get("allowed_policies")
    if (not isinstance(policies, list) or not 1 <= len(policies) <= 12
            or any(not isinstance(x, str) or OID.fullmatch(x) is None
                   for x in policies) or len(set(policies)) != len(policies)):
        return "INVALID_TSA_POLICY_CONFIG"
    return None


def _parse_token_text(data):
    """Extract signed genTime and policy after a parseable token was supplied.

    genTime is considered cryptographically credible ONLY after full ts
    signature/imprint verification; merely parsing text never establishes
    a trustworthy timestamp.
    """
    text = data.decode("utf-8", errors="replace")
    match_time = re.findall(r"(?m)^Time stamp:\s*(.+?)\s*$", text)
    match_policy = re.findall(r"(?m)^Policy OID:\s*(\S+)\s*$", text)
    match_hash = re.findall(r"(?m)^Hash Algorithm:\s*(\S+)\s*$", text)
    if len(match_time) != 1 or len(match_policy) != 1 or len(match_hash) != 1:
        raise ValueError("token fields missing or ambiguous")
    if match_hash[0].lower() != "sha256":
        raise ValueError("unsupported RFC3161 digest algorithm")
    raw = re.sub(r"\s+", " ", match_time[0].strip())
    if not raw.endswith(" GMT"):
        raise ValueError("non GMT timestamp")
    clean = raw[:-4]
    try:
        dt = datetime.strptime(clean, "%b %d %H:%M:%S.%f %Y")
    except ValueError:
        dt = datetime.strptime(clean, "%b %d %H:%M:%S %Y")
    return dt.replace(tzinfo=timezone.utc), match_policy[0]


def _verify_token(token, data, trust, *, crl_pem=None):
    """Verify CMS signer is exactly pinned TSA + RFC3161 imprint + X509 path."""
    with tempfile.TemporaryDirectory(prefix="kpl15-token-") as folder:
        directory = Path(folder)
        files = {
            "token": directory / "token.der",
            "message": directory / "signed-envelope.bin",
            "tsa": directory / "tsa.pem",
            "root": directory / "root.pem",
            "content": directory / "ignored-content.bin",
        }
        files["token"].write_bytes(token)
        files["message"].write_bytes(data)
        files["tsa"].write_text(trust["tsa_cert_pem"], encoding="ascii")
        files["root"].write_text(trust["root_ca_pem"], encoding="ascii")
        info = _run(["openssl", "ts", "-reply", "-in", str(files["token"]),
                     "-token_in", "-text"])
        if info.returncode:
            return ("RFC3161_TOKEN_UNREADABLE", False, False, False, False)
        try:
            gen, policy = _parse_token_text(info.stdout)
        except ValueError:
            return ("RFC3161_TOKEN_FIELDS_INVALID", False, False, False, False)
        if policy not in trust["allowed_policies"]:
            return ("TSA_POLICY_NOT_ALLOWLISTED", False, False, False, False)
        # First force exact signer cert rather than trusting *any* leaf with
        # a path to the pinned CA. -nointern disallows token supplied certs.
        signed = _run([
            "openssl", "cms", "-verify", "-inform", "DER",
            "-in", str(files["token"]), "-binary", "-nointern", "-noverify",
            "-certfile", str(files["tsa"]), "-out", str(files["content"]),
        ])
        if signed.returncode:
            return ("PINNED_TSA_SIGNER_MISMATCH", False, False, False, False)
        # A valid CMS signature alone does not validate the RFC3161 imprint,
        # signingCertificate ESSCertID, TSA-specific EKU or X509 path.
        checked = _run([
            "openssl", "ts", "-verify", "-token_in", "-in", str(files["token"]),
            "-data", str(files["message"]), "-CAfile", str(files["root"]),
            "-untrusted", str(files["tsa"]), "-purpose", "timestampsign",
            "-attime", str(int(gen.timestamp())),
        ])
        if checked.returncode:
            return ("RFC3161_IMPRINT_SIGNATURE_OR_CERT_PATH_INVALID",
                    False, False, False, False)
        if crl_pem is None:
            return (gen, True, True, False, True)
        if (not isinstance(crl_pem, str) or not 0 < len(crl_pem) <= MAX_CRL
                or not crl_pem.startswith("-----BEGIN X509 CRL-----")):
            return ("INVALID_REVOCATION_EVIDENCE", True, True, False, True)
        crl = directory / "status.crl"
        crl.write_text(crl_pem, encoding="ascii")
        # Offline CRL check, no URL fetching, at the token genTime. This only
        # covers the leaf in this prototype, not lifecycle-wide revocation.
        rev = _run([
            "openssl", "verify", "-purpose", "timestampsign",
            "-attime", str(int(gen.timestamp())), "-CAfile",
            str(files["root"]), "-CRLfile", str(crl),
            "-crl_check", str(files["tsa"]),
        ])
        if rev.returncode:
            return ("CRL_REVOKED_STALE_OR_INVALID", True, True, False, True)
        return (gen, True, True, True, True)


def verify_rfc3161_offline(archive_path, signed_envelope, trusted_ed25519_keys,
                           token_b64, tsa_trust, *, revocation_crl_pem=None):
    """Offline verification, never grants trusted timestamp or production status.

    TSA token must imprint the complete canonical Ed25519 signed *envelope*,
    not just the forecast/payload. Out-of-band trust pins and real external
    revocation/time-service identities remain human-reviewed prerequisites.
    """
    try:
        snapshot = read_verified_archive_snapshot(archive_path)
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError):
        return _hold(["INVALID_OR_MISSING_ARCHIVE"])
    signature = _inspect_signed(
        snapshot["entries"], signed_envelope, trusted_ed25519_keys)
    if not signature["pinned_signature_verified"]:
        return _hold(["ED25519_RECEIPT_INVALID"] + signature["reasons"])
    if not isinstance(token_b64, str) or len(token_b64) > (MAX_TOKEN * 4 // 3 + 8):
        return _hold(["INVALID_RFC3161_TOKEN_ENCODING"], signed=True)
    try:
        token = base64.b64decode(token_b64, validate=True)
        if not token or len(token) > MAX_TOKEN:
            raise ValueError("token too large or empty")
    except (ValueError, binascii.Error):
        return _hold(["INVALID_RFC3161_TOKEN_ENCODING"], signed=True)
    pin_error = _pin_trust(tsa_trust)
    if pin_error:
        return _hold([pin_error], signed=True)
    try:
        message = json.dumps(
            signed_envelope, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
        checked, token_ok, chain_ok, revocation_ok, parsed = _verify_token(
            token, message, tsa_trust, crl_pem=revocation_crl_pem)
    except (RuntimeError, ValueError, TypeError, UnicodeError):
        return _hold(["CRYPTO_BACKEND_UNAVAILABLE_OR_INVALID"], signed=True)
    if not parsed:
        return _hold([checked], signed=True, token=token_ok, chain=chain_ok)
    if isinstance(checked, str):
        return _hold([checked], signed=True, token=token_ok, chain=chain_ok,
                     revocation=revocation_ok)
    gen = checked
    row = snapshot["entries"][signed_envelope["payload"]["record_index"] - 1]["forecast"]
    signed_witness = _time(signed_envelope["payload"]["witnessed_at"])
    try:
        in_window = signed_witness <= gen < _time(row["game_start_at"])
    except (ValueError, TypeError):
        in_window = False
    reasons = []
    if not in_window:
        reasons.append("TSA_TIME_OUTSIDE_SIGNED_FORECAST_WINDOW")
    if not revocation_ok:
        reasons.append("REVOCATION_STATUS_UNAVAILABLE")
    reasons.extend([
        "EXTERNAL_TSA_IDENTITY_AND_TRUST_ROOT_NOT_INDEPENDENTLY_ATTESTED",
        "EVIDENCE_OF_PRE_GAME_RECEIPT_DELIVERY_UNVERIFIED",
        "KPL_SOURCE_RIGHTS_AND_MODEL_CALIBRATION_UNVERIFIED",
    ])
    return _hold(reasons, signed=True, token=token_ok, chain=chain_ok,
                 window=in_window, revocation=revocation_ok)
