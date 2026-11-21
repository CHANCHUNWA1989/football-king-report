"""Offline RFC3161-to-forecast-byte bridge; untrusted research preflight ONLY.

This locally invokes OpenSSL, whose -digest argument is exactly SHA256 of
validated ORIGINAL manifest bytes. Never trusts supplied success flags or
allows a caller to substitute another receipt after manifest verification.
A successful local cryptographic check is NOT a certified football case.
PR #463 remains the separate TSA-policy review; no TSA policy is approved here.
"""
import argparse
from datetime import timedelta, datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from first_case_payload_binding import audit as audit_bytes, _read_file, _time

SCHEMA = "football-king-first-case-rfc3161-link-v1"
MAX_TOKEN_BYTES = 2_000_000
MAX_CA_BYTES = 1_000_000
_STAMP = re.compile(
    r"^Time stamp:\s*([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\d{4})\s+GMT\s*$",
    re.MULTILINE,
)


def _hold(reason, case=None):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "fixture_id_claim": case.get("fixture_id_claim") if case else None,
        "byte_digest_binding_checked": bool(case and case.get("byte_digest_binding_checked")),
        "manifest_sha256": case.get("manifest_sha256") if case else None,
        "local_openssl_signature_and_imprint_checked": False,
        "tsa_gen_time_utc_claim": None,
        "tsa_trust_policy_verified": False,
        "forecast_capture_time_independently_authenticated": False,
        "fixture_identity_source_native_authenticated": False,
        "market_quote_executable_authenticated": False,
        "independent_second_ft_source_authenticated": False,
        "regulation_ft_settlement_authenticated": False,
        "certified_forward_case_count": 0,
        "positive_ev_verified": False,
        "eligible_for_model_scoring": False,
        "model_promotion_allowed": False,
        "production_recommendations": "DISABLED",
        "recommended_stake": None,
    }


def _safe_file(value, max_bytes):
    path = Path(value)
    if (path.is_symlink() or not path.is_file()
            or not 1 <= path.stat().st_size <= max_bytes):
        raise ValueError("MISSING_OR_UNSAFE_TSA_INPUT")
    return path


def check(forecast_raw, quote_raw, manifest_raw, *,
          token_path, ca_path, openssl="openssl", runner=subprocess.run):
    """Bind OpenSSL's verification to exact previously audited manifest bytes.

    No claim of independent TSA policy, actual bookmaker execution, upstream
    provider authenticity, future model skill or betting eligibility.
    """
    case = audit_bytes(forecast_raw, quote_raw, manifest_raw)
    if not case.get("byte_digest_binding_checked"):
        return _hold("BYTE_BINDING_FAILED:" + case["reason"], case)
    try:
        token = _safe_file(token_path, MAX_TOKEN_BYTES)
        trust = _safe_file(ca_path, MAX_CA_BYTES)
        if token.resolve() == trust.resolve():
            raise ValueError("TSA_TOKEN_AND_CA_MUST_DIFFER")
        if type(openssl) is not str or not openssl or openssl.startswith("-"):
            raise ValueError("INVALID_OPENSSL_EXECUTABLE")
        # Read original raw manifest only AFTER first-case byte binding. The
        # "-digest" form prevents file-path swap/TOCTOU on the manifest.
        manifest = json.loads(manifest_raw)
        manifest_created = _time(manifest["created_utc"])
        kickoff = _time(manifest["kickoff_utc"])
        # Pin token + CA bytes in a private temporary directory. Two OpenSSL
        # calls MUST read the same staged token, never a mutable source path.
        token_bytes, trust_bytes = token.read_bytes(), trust.read_bytes()
        if (not 1 <= len(token_bytes) <= MAX_TOKEN_BYTES
                or not 1 <= len(trust_bytes) <= MAX_CA_BYTES):
            raise ValueError("MISSING_OR_UNSAFE_TSA_INPUT")
        with tempfile.TemporaryDirectory(prefix="football-king-tsa-") as folder:
            staged_token, staged_ca = (
                Path(folder)/"token.tsr", Path(folder)/"reviewed-ca.pem")
            for staged, original in (
                (staged_token, token_bytes), (staged_ca, trust_bytes)):
                staged.write_bytes(original)
                os.chmod(staged, 0o600)
            command = [
                openssl, "ts", "-verify", "-in", str(staged_token),
                "-digest", case["manifest_sha256"],
                "-CAfile", str(staged_ca),
            ]
            verified = runner(command, capture_output=True, text=True,
                              timeout=20, check=False)
            if verified.returncode != 0:
                raise ValueError("TSA_SIGNATURE_OR_MANIFEST_IMPRINT_UNTRUSTED")
            inspected = runner(
                [openssl, "ts", "-reply", "-in", str(staged_token), "-text"],
                capture_output=True, text=True, timeout=20, check=False)
            if (staged_token.read_bytes() != token_bytes
                    or staged_ca.read_bytes() != trust_bytes):
                raise ValueError("STAGED_TSA_INPUT_CHANGED")
            if inspected.returncode != 0 or type(inspected.stdout) is not str:
                raise ValueError("INVALID_TIMESTAMP_TOKEN")
        if len(inspected.stdout) > 100_000:
            raise ValueError("OVERSIZED_TIMESTAMP_DESCRIPTION")
        found = _STAMP.findall(inspected.stdout)
        if len(found) != 1:
            raise ValueError("UNRECOGNIZED_TIMESTAMP_FORMAT")
        month, day, clock, year = found[0]
        signed_time = datetime.strptime(
            f"{month} {day} {clock} {year}", "%b %d %H:%M:%S %Y",
        ).replace(tzinfo=timezone.utc)
        if signed_time < manifest_created:
            raise ValueError("TOKEN_PREDATES_DECLARED_MANIFEST")
        if signed_time > kickoff - timedelta(minutes=10):
            raise ValueError("TOKEN_NOT_SAFELY_BEFORE_KICKOFF")
        return {
            **_hold("LOCAL_RFC3161_CHECK_PASSED_TSA_POLICY_AND_SOURCES_STILL_UNVERIFIED", case),
            "local_openssl_signature_and_imprint_checked": True,
            "tsa_gen_time_utc_claim": signed_time.isoformat(),
        }
    except (ValueError, TypeError, OSError, subprocess.TimeoutExpired,
            AttributeError, OverflowError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else "TSA_VERIFIER_ERROR"
        return _hold(reason, case)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--forecast", required=True)
    p.add_argument("--quote", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--ca", required=True)
    args = p.parse_args(argv)
    try:
        result = check(
            _read_file(args.forecast), _read_file(args.quote),
            _read_file(args.manifest),
            token_path=args.token, ca_path=args.ca)
    except (ValueError, OSError) as exc:
        result = _hold(str(exc) if isinstance(exc, ValueError)
                       else "FILE_READ_FAILED")
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    if not result["local_openssl_signature_and_imprint_checked"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
