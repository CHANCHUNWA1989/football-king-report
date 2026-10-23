"""Research-only entry point with separately loaded local entitlements.

The provider payload cannot supply or choose the entitlement registry.
A local operator must supply a trusted path to a reviewed JSON registry.
No live network calls, production recommendations or credential handling.
"""
import json
from pathlib import Path
from live_entitlement_gate import admit_with_registry


def admit_from_local_registry(raw, *, registry_path=None, now=None):
    hold = {"status": "HOLD", "reason": "LOCAL_ENTITLEMENTS_UNAVAILABLE",
            "production_recommendations": "DISABLED", "observations": []}
    if not isinstance(registry_path, (str, Path)):
        return hold
    try:
        path = Path(registry_path)
        if not path.is_file() or path.stat().st_size > 65536:
            return hold
        with path.open("r", encoding="utf-8") as stream:
            registry = json.load(stream)
    except (OSError, ValueError, UnicodeError, TypeError):
        return hold
    if not isinstance(registry, dict):
        return hold
    return admit_with_registry(raw, registry, now=now)
