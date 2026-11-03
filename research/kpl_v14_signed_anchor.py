"""Offline Ed25519 signature and pinned-key checks for KPL archive anchor claims.

Research-only. A mathematically valid signature from an operator-supplied public
key does NOT prove independent witness identity, trustworthy clock, data rights,
or an actual pre-game submission. The source contains no pinned production keys
and never signs, network-connects, settles odds, or enables betting.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from research.kpl_v11_forecast_archive import _time
from research.kpl_v13_archive_snapshot import read_verified_archive_snapshot

SCHEMA = "kpl-ed25519-anchor-v1"
TARGET = "INDEPENDENT_TIMESTAMP_SERVICE"
ENVELOPE_KEYS = frozenset({"payload", "key_id", "signature_b64"})
PAYLOAD_KEYS = frozenset({
    "schema", "record_index", "head_hash", "prediction_id", "series_id",
    "game_number", "team_ids", "model_version", "forecast_at",
    "game_start_at", "anchor_target", "witnessed_at", "nonce"})
# RFC 8410 Ed25519 SubjectPublicKeyInfo DER header, followed by exactly 32 bytes.
ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
LOWER_HEX = re.compile(r"^[0-9a-f]{64}$")
NONCE = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")


def canonical_signed_message(payload):
    """Stable UTF-8 message bytes for Ed25519 signing/verification.

    Both sides must sign this exact canonical JSON representation, never
    a pretty-printed or key-order-dependent text form.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _is_id(value):
    return (isinstance(value, str) and not isinstance(value, bool)
            and 0 < len(value) <= 128 and value.strip() == value)


def _message_from_row(entry, index, witnessed_at, nonce):
    row = entry["forecast"]
    return {"schema": SCHEMA, "record_index": index,
            "head_hash": entry["entry_hash"],
            "prediction_id": row["prediction_id"],
            "series_id": row["series_id"],
            "game_number": row["game_number"],
            "team_ids": row["team_ids"],
            "model_version": row["model_version"],
            "forecast_at": row["forecast_at"],
            "game_start_at": row["game_start_at"],
            "anchor_target": TARGET,
            "witnessed_at": witnessed_at,
            "nonce": nonce}


def build_unsigned_anchor_payload(archive_path, record_index, *, witnessed_at, nonce):
    """Construct unsigned, identity-bound message; DOES NOT sign or timestamp."""
    snapshot = read_verified_archive_snapshot(archive_path)
    if type(record_index) is not int or not 1 <= record_index <= len(snapshot["entries"]):
        raise ValueError("invalid record index")
    if not isinstance(nonce, str) or NONCE.fullmatch(nonce) is None:
        raise ValueError("invalid nonce")
    row = snapshot["entries"][record_index - 1]["forecast"]
    witnessed = _time(witnessed_at)
    if not _time(row["forecast_at"]) <= witnessed < _time(row["game_start_at"]):
        raise ValueError("invalid witness time for research signing payload")
    return _message_from_row(snapshot["entries"][record_index - 1],
                             record_index, witnessed_at, nonce)


def _hold(reasons, *, pinned=False, bound=False):
    return {"status": "HOLD", "reasons": list(dict.fromkeys(reasons)),
            "pinned_signature_verified": bool(pinned),
            "archive_binding_verified": bool(bound),
            "external_timestamp_authenticated": False,
            "witness_identity_independently_verified": False,
            "provider_data_rights_verified": False,
            "research_only": True, "live_execution_allowed": False,
            "production_recommendations": "DISABLED"}


def _run(command, *, data=None):
    """Use OS OpenSSL Ed25519, never a homemade crypto implementation."""
    try:
        return subprocess.run(command, input=data, capture_output=True,
                              timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("CRYPTO_BACKEND_UNAVAILABLE") from exc


def _verify_signature(payload, signature, trusted_config):
    """Check separate operator-pinned Ed25519 public key and detached signature."""
    if not isinstance(trusted_config, dict) or set(trusted_config) != {
            "public_key_pem", "spki_sha256"}:
        return "INVALID_PIN_CONFIG"
    pem = trusted_config["public_key_pem"]
    pin = trusted_config["spki_sha256"]
    if (not isinstance(pem, str) or not pem.startswith("-----BEGIN PUBLIC KEY-----")
            or len(pem.encode("utf-8")) > 4096
            or not isinstance(pin, str) or LOWER_HEX.fullmatch(pin) is None):
        return "INVALID_PIN_CONFIG"
    try:
        der_result = _run(["openssl", "pkey", "-pubin", "-inform", "PEM",
                           "-outform", "DER"], data=pem.encode("utf-8"))
    except RuntimeError:
        return "CRYPTO_BACKEND_UNAVAILABLE"
    der = der_result.stdout
    if (der_result.returncode != 0 or len(der) != 44
            or not der.startswith(ED25519_SPKI_PREFIX)):
        return "UNSUPPORTED_OR_INVALID_PUBLIC_KEY"
    if hashlib.sha256(der).hexdigest() != pin:
        return "PINNED_PUBLIC_KEY_MISMATCH"
    try:
        with tempfile.TemporaryDirectory(prefix="kpl-verify-") as d:
            pub = Path(d) / "public.pem"
            sig = Path(d) / "signature.bin"
            msg = Path(d) / "signed-message.bin"
            pub.write_bytes(pem.encode("utf-8"))
            sig.write_bytes(signature)
            msg.write_bytes(canonical_signed_message(payload))
            result = _run(["openssl", "pkeyutl", "-verify", "-rawin",
                           "-pubin", "-inkey", str(pub),
                           "-sigfile", str(sig), "-in", str(msg)])
    except (RuntimeError, OSError, TypeError, ValueError):
        return "CRYPTO_BACKEND_UNAVAILABLE"
    return None if result.returncode == 0 else "SIGNATURE_INVALID"


def _inspect_signed(entries, envelope, trusted_keys):
    if (not isinstance(envelope, dict) or set(envelope) != ENVELOPE_KEYS
            or not isinstance(envelope.get("payload"), dict)
            or set(envelope["payload"]) != PAYLOAD_KEYS
            or not _is_id(envelope.get("key_id"))
            or not isinstance(envelope.get("signature_b64"), str)):
        return _hold(["INVALID_SIGNED_ENVELOPE"])
    payload = envelope["payload"]
    index = payload["record_index"]
    if (payload["schema"] != SCHEMA
            or type(index) is not int or not 1 <= index <= len(entries)
            or not isinstance(payload["nonce"], str)
            or NONCE.fullmatch(payload["nonce"]) is None
            or payload["anchor_target"] != TARGET
            or not isinstance(payload["team_ids"], list)
            or any(not _is_id(x) for x in payload["team_ids"])):
        return _hold(["INVALID_SIGNED_PAYLOAD"])
    expected = _message_from_row(entries[index - 1], index,
                                 payload["witnessed_at"], payload["nonce"])
    if payload != expected:
        return _hold(["ARCHIVE_EVENT_BINDING_MISMATCH"])
    try:
        witness = _time(payload["witnessed_at"])
        row = entries[index - 1]["forecast"]
        if not _time(row["forecast_at"]) <= witness < _time(row["game_start_at"]):
            return _hold(["WITNESS_TIME_INVALID"])
    except (TypeError, ValueError):
        return _hold(["WITNESS_TIME_INVALID"])
    try:
        raw = base64.b64decode(envelope["signature_b64"], validate=True)
        if len(raw) != 64:
            raise ValueError("wrong Ed25519 signature length")
    except (ValueError, binascii.Error):
        return _hold(["INVALID_SIGNATURE_ENCODING"], bound=True)
    if not isinstance(trusted_keys, dict) or envelope["key_id"] not in trusted_keys:
        return _hold(["KEY_NOT_PINNED"], bound=True)
    error = _verify_signature(payload, raw, trusted_keys[envelope["key_id"]])
    if error is not None:
        return _hold([error], bound=True)
    return _hold(["EXTERNAL_WITNESS_IDENTITY_AND_TIME_NOT_INDEPENDENTLY_CONFIRMED"],
                 pinned=True, bound=True)


def verify_signed_anchor_receipt(archive_path, envelope, trusted_keys):
    """Verify one signature and archive binding; HOLD even when crypto verifies."""
    try:
        snapshot = read_verified_archive_snapshot(archive_path)
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError):
        return _hold(["INVALID_OR_MISSING_ARCHIVE"])
    return _inspect_signed(snapshot["entries"], envelope, trusted_keys)


def audit_signed_anchor_batch(archive_path, envelopes, trusted_keys):
    """One-snapshot, all-record signature coverage and nonce uniqueness gate.

    Only verifies signatures against the keyring separately configured by the
    caller. The keyring's provenance is NOT authenticated by this function.
    """
    try:
        snapshot = read_verified_archive_snapshot(archive_path)
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError):
        return {"status": "HOLD", "signed_receipt_coverage_passed": False,
                "signed_receipt_count": 0,
                "reasons": ["INVALID_OR_MISSING_ARCHIVE"],
                "external_timestamp_authenticated": False,
                "production_recommendations": "DISABLED",
                "research_only": True, "live_execution_allowed": False}
    entries = snapshot["entries"]
    issues, indices, nonces = [], set(), set()
    if not isinstance(envelopes, list) or len(envelopes) > len(entries):
        issues.append("INVALID_SIGNED_RECEIPT_COLLECTION")
    else:
        for envelope in envelopes:
            inspection = _inspect_signed(entries, envelope, trusted_keys)
            if not inspection["pinned_signature_verified"]:
                issues.append("SIGNED_RECEIPT_INVALID")
            payload = envelope.get("payload") if isinstance(envelope, dict) else None
            if not isinstance(payload, dict):
                issues.append("INVALID_SIGNED_RECEIPT_COLLECTION")
                continue
            idx, nonce = payload.get("record_index"), payload.get("nonce")
            if type(idx) is not int or idx in indices:
                issues.append("DUPLICATE_SIGNED_RECORD_INDEX")
            else:
                indices.add(idx)
            if not isinstance(nonce, str) or nonce in nonces:
                issues.append("DUPLICATE_ANCHOR_NONCE")
            else:
                nonces.add(nonce)
    if indices != set(range(1, len(entries) + 1)):
        issues.append("SIGNATURE_COVERAGE_INCOMPLETE")
    passed = not issues
    return {"status": "HOLD",
            "signed_receipt_coverage_passed": passed,
            "signed_receipt_count": len(indices),
            "reasons": list(dict.fromkeys(issues)) +
                       ["EXTERNAL_WITNESS_IDENTITY_AND_TIME_NOT_INDEPENDENTLY_CONFIRMED",
                        "PROVIDER_DATA_RIGHTS_UNVERIFIED",
                        "MODEL_CALIBRATION_NOT_VERIFIED"],
            "external_timestamp_authenticated": False,
            "witness_identity_independently_verified": False,
            "provider_data_rights_verified": False,
            "research_only": True, "live_execution_allowed": False,
            "production_recommendations": "DISABLED"}
