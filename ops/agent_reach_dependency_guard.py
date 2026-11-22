"""Fail-closed runtime dependency-version guard for the Agent Reach smoke runner.

This ONLY checks version equality and an exact constraints inventory.
It does NOT attest wheel hashes, supply-chain security, or external data.
"""
from __future__ import annotations

import argparse
import json
import re
from importlib import metadata
from pathlib import Path

EXPECTED = {
    "agent-reach": "1.6.1",
    "brotli": "1.2.1",
    "certifi": "2026.11.20",
    "charset-normalizer": "3.5.2",
    "idna": "3.20",
    "loguru": "0.8.0",
    "mutagen": "1.48.1",
    "pycryptodomex": "3.24.2",
    "pyyaml": "6.0.4",
    "requests": "2.34.2",
    "urllib3": "2.8.0",
    "websockets": "17.4",
    "yt-dlp": "2026.8.19",
    "yt-dlp-ejs": "0.8.0",
}
_LINE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9._+!-]*)\Z")


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_constraints(data: str) -> dict[str, str]:
    if not isinstance(data, str) or len(data) > 10_000:
        raise ValueError("INVALID_CONSTRAINTS")
    out: dict[str, str] = {}
    for line in data.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE.fullmatch(line)
        if match is None:
            raise ValueError("CONSTRAINT_NOT_EXACT_PIN")
        name, version = canonical(match.group(1)), match.group(2)
        if name in out:
            raise ValueError("DUPLICATE_DEPENDENCY")
        out[name] = version
    if out != EXPECTED:
        raise ValueError("CONSTRAINT_INVENTORY_DRIFT")
    return out


def audit(constraints: str, version_reader=metadata.version) -> tuple[dict, int]:
    report = {
        "schema": "agent-reach-smoke-dependency-check-v1",
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "supply_chain_hash_verified": False,
        "build_isolation_hash_verified": False,
        "egress_firewall_verified": False,
        "eligible_for_model": False,
        "verified_positive_ev": None,
        "dependency_version_check": "HOLD",
        "checked_packages": 0,
        "reason": "NOT_CHECKED",
    }
    try:
        pins = parse_constraints(constraints)
        for name, wanted in pins.items():
            try:
                actual = version_reader(name)
            except (metadata.PackageNotFoundError, KeyError, LookupError):
                raise ValueError("PINNED_DEPENDENCY_MISSING") from None
            if actual != wanted:
                raise ValueError("PINNED_DEPENDENCY_VERSION_DRIFT")
            report["checked_packages"] += 1
        report["dependency_version_check"] = "PASS_VERSION_ONLY"
        report["reason"] = "ALL_DECLARED_VERSIONS_MATCH"
        return report, 0
    except (ValueError, TypeError) as exc:
        report["reason"] = str(exc)[:64] if isinstance(exc, ValueError) else "INVALID_INPUT"
        return report, 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--constraints", type=Path, required=True)
    args = parser.parse_args()
    try:
        constraints = args.constraints.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        print(json.dumps({"status": "HOLD", "dependency_version_check": "HOLD",
                          "production_recommendations": "DISABLED", "reason": "READ_FAILED"}))
        return 2
    result, rc = audit(constraints)
    print(json.dumps(result, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
