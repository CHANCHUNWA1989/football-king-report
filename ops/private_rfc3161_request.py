"""Minimal RFC 3161 SHA-256 TimeStampReq encoder (request only).

Does not verify a TimeStampResp, TSA signature, certificate chain, or time.
"""
import hashlib
import secrets
from ops.private_forecast_snapshot import verify


def _length(n):
    if n < 0:
        raise ValueError("INVALID_DER_LENGTH")
    if n < 128:
        return bytes([n])
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _tlv(tag, data):
    return bytes([tag]) + _length(len(data)) + data


def _integer(n):
    if type(n) is not int or n <= 0 or n >= 2 ** 128:
        raise ValueError("INVALID_NONCE")
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return _tlv(0x02, raw)


def make_request(snapshot, *, nonce=None):
    verify(snapshot)
    if nonce is None:
        nonce = secrets.randbits(127) | 1
    # SHA-256 AlgorithmIdentifier: id-sha256 + NULL.
    algorithm = bytes.fromhex("300d06096086480165030402010500")
    digest = hashlib.sha256(bytes.fromhex(snapshot["sha256"])).digest()
    imprint = _tlv(0x30, algorithm + _tlv(0x04, digest))
    # version 1, messageImprint, nonce, certReq TRUE.
    der = _tlv(0x30, _integer(1) + imprint + _integer(nonce) + b"\x01\x01\xff")
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "content_type": "application/timestamp-query",
            "request_der_hex": der.hex(), "nonce": nonce,
            "message_imprint_sha256": digest.hex(),
            "imprint_input": "raw_snapshot_sha256_digest_bytes",
            "tsa_response_verified": False,
            "capture_time_independently_attested": False}


def reject_unverified_response(response_der):
    if not isinstance(response_der, bytes) or not response_der:
        raise ValueError("INVALID_TIMESTAMP_RESPONSE")
    # Explicitly fail closed until CMS signature, nonce, imprint and PKIX validation exist.
    raise ValueError("RFC3161_RESPONSE_VERIFICATION_NOT_IMPLEMENTED")
