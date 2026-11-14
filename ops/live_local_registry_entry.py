"""Research-only entry point with separately loaded local entitlements.

The provider payload cannot supply or choose the entitlement registry.
A local operator must supply a trusted path to a reviewed JSON registry.
No live network calls, production recommendations or credential handling.
"""
import hashlib
import hmac
import json
from pathlib import Path
from live_entitlement_gate import admit_with_registry


def admit_from_local_registry(raw, *, registry_path=None, expected_sha256=None, now=None):
    hold = {"status": "HOLD", "reason": "LOCAL_ENTITLEMENTS_UNAVAILABLE",
            "production_recommendations": "DISABLED", "observations": []}
    if (not isinstance(registry_path, (str, Path))
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha256)):
        return hold
    try:
        path = Path(registry_path)
        if not path.is_file() or path.stat().st_size > 65536:
            return hold
        content = path.read_bytes()
        if len(content) > 65536 or not hmac.compare_digest(
                hashlib.sha256(content).hexdigest(), expected_sha256):
            return hold
        registry = json.loads(content.decode("utf-8"))
    except (OSError, ValueError, UnicodeError, TypeError):
        return hold
    if not isinstance(registry, dict):
        return hold
    return admit_with_registry(raw, registry, now=now)
