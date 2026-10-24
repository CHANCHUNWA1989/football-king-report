"""Validate operator-pinned Ed25519 public-key registry (no self-trust).

The registry must be obtained through an authenticated, independent channel.
A registry file and digest supplied by the same untrusted actor prove nothing.
"""
import base64
import hashlib
import json
import re
from pathlib import Path


def load_trusted_key_registry(path, *, expected_sha256, key_id):
    hold = {"status": "HOLD", "reason": "UNTRUSTED_KEY_REGISTRY",
            "production_recommendations": "DISABLED"}
    if (not isinstance(path, (str, Path))
            or not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256) is None
            or not isinstance(key_id, str) or not key_id.strip()):
        return hold
    try:
        source = Path(path)
        if source.stat().st_size > 100_000:
            return hold
        with source.open("rb") as stream:
            raw = stream.read(100_001)
        if (len(raw) > 100_000
                or hashlib.sha256(raw).hexdigest() != expected_sha256.lower()):
            return hold
        def reject_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result
        document = json.loads(
            raw, object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, ValueError, TypeError, RecursionError, UnicodeDecodeError):
        return hold
    if (not isinstance(document, dict)
            or set(document) != {"schema_version", "keys"}
            or type(document["schema_version"]) is not int
            or document["schema_version"] != 1
            or not isinstance(document["keys"], list)
            or not 1 <= len(document["keys"]) <= 100):
        return hold
    seen = set()
    selected = None
    for entry in document["keys"]:
        if (not isinstance(entry, dict)
                or set(entry) != {"key_id", "algorithm", "public_key_b64", "status"}
                or not isinstance(entry["key_id"], str)
                or not entry["key_id"].strip()
                or entry["key_id"] in seen
                or entry["algorithm"] != "Ed25519"
                or entry["status"] not in ("active", "revoked")
                or not isinstance(entry["public_key_b64"], str)):
            return hold
        seen.add(entry["key_id"])
        try:
            public_key = base64.b64decode(entry["public_key_b64"], validate=True)
        except (ValueError, base64.binascii.Error):
            return hold
        if len(public_key) != 32:
            return hold
        if entry["key_id"] == key_id and entry["status"] == "active":
            selected = entry["public_key_b64"]
    if selected is None:
        return hold
    return {"status": "RESEARCH_ONLY", "reason": "PINNED_ACTIVE_KEY_SELECTED",
            "key_id": key_id, "public_key_b64": selected,
            "registry_sha256": expected_sha256.lower(),
            "issuer_identity_verified": False,
            "production_recommendations": "DISABLED"}
