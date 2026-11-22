"""SHA-256 wheel inventory guard for Agent Reach's external runtime packages.

Pins actual wheel FILE bytes, not just PyPI distribution versions.
Discovery is only a *candidate* report. Verification needs a separate
committed manifest, and does not attest signatures, build deps or egress.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from agent_reach_dependency_guard import EXPECTED, canonical

SCHEMA = "agent-reach-runtime-wheel-sha256-v1"
EXTERNAL = {k: v for k, v in EXPECTED.items() if k != "agent-reach"}
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+]*\.whl\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_WHEEL_BYTES = 70_000_000


class WheelHold(ValueError):
    """Invalid or incomplete wheelhouse."""


def _identity(filename: str) -> tuple[str, str]:
    if not isinstance(filename, str) or len(filename) > 220 or not NAME_RE.fullmatch(filename):
        raise WheelHold("INVALID_WHEEL_NAME")
    pieces = filename[:-4].split("-")
    if len(pieces) != 5:
        raise WheelHold("INVALID_WHEEL_TAGS")
    name, version = canonical(pieces[0]), pieces[1]
    if not version or name not in EXTERNAL or EXTERNAL[name] != version:
        raise WheelHold("WHEEL_VERSION_OR_NAME_MISMATCH")
    if any(not part for part in pieces[2:]):
        raise WheelHold("INVALID_WHEEL_TAGS")
    return name, version


def _hash_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise WheelHold("UNSAFE_WHEEL_PATH")
    if path.stat().st_size > MAX_WHEEL_BYTES or path.stat().st_size == 0:
        raise WheelHold("WHEEL_SIZE_OUT_OF_RANGE")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover(wheelhouse: Path) -> dict:
    if not wheelhouse.is_dir() or wheelhouse.is_symlink():
        raise WheelHold("WHEELHOUSE_MISSING")
    items = []
    found = set()
    for path in sorted(wheelhouse.iterdir()):
        if path.suffix != ".whl":
            raise WheelHold("NON_WHEEL_IN_DIRECTORY")
        name, _ = _identity(path.name)
        if name in found:
            raise WheelHold("DUPLICATE_WHEEL_PACKAGE")
        found.add(name)
        items.append({"file": path.name, "sha256": _hash_file(path)})
    if found != set(EXTERNAL):
        raise WheelHold("INCOMPLETE_WHEEL_INVENTORY")
    return {"schema": SCHEMA, "wheels": items}


def verify(wheelhouse: Path, manifest: object) -> tuple[dict, str]:
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "wheels"} or manifest.get("schema") != SCHEMA:
        raise WheelHold("INVALID_HASH_MANIFEST")
    rows = manifest.get("wheels")
    if not isinstance(rows, list) or len(rows) != len(EXTERNAL):
        raise WheelHold("INVALID_HASH_MANIFEST")
    expected = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"file", "sha256"}:
            raise WheelHold("INVALID_HASH_MANIFEST")
        name, _ = _identity(row.get("file"))
        hashval = row.get("sha256")
        if not isinstance(hashval, str) or not SHA_RE.fullmatch(hashval):
            raise WheelHold("INVALID_HASH_MANIFEST")
        if name in expected:
            raise WheelHold("DUPLICATE_HASH_MANIFEST_PACKAGE")
        expected[name] = (row["file"], hashval)
    actual = discover(wheelhouse)
    observed = { _identity(row["file"])[0]: (row["file"], row["sha256"])
                 for row in actual["wheels"] }
    if expected != observed:
        raise WheelHold("WHEEL_BYTES_OR_FILENAME_MISMATCH")
    # pip's own --require-hashes verification is an independent second gate.
    requirements = "".join(
        f"{name}=={EXTERNAL[name]} --hash=sha256:{expected[name][1]}\n"
        for name in sorted(expected)
    )
    report = {
        "schema": "agent-reach-runtime-wheel-verification-v1",
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "runtime_wheel_hash_verified": True,
        "runtime_wheel_count": len(expected),
        "build_dependency_hash_verified": False,
        "upstream_signature_verified": False,
        "egress_firewall_verified": False,
        "eligible_for_model": False,
        "verified_positive_ev": None,
        "reason": "EXTERNAL_RUNTIME_WHEEL_BYTES_MATCH_COMMITTED_HASHES",
    }
    return report, requirements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", required=True, type=Path)
    p = parser.add_mutually_exclusive_group(required=True)
    p.add_argument("--discover-output", type=Path)
    p.add_argument("--manifest", type=Path)
    parser.add_argument("--requirements-output", type=Path)
    args = parser.parse_args()
    try:
        if args.discover_output is not None:
            # Discovery is evidence gathering, not verification and cannot promote.
            if args.requirements_output is not None:
                raise WheelHold("DISCOVERY_CANNOT_EMIT_INSTALL_REQUIREMENTS")
            data = discover(args.wheelhouse)
            args.discover_output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print("WHEEL_DISCOVERY_ONLY: UNVERIFIED_CANDIDATE")
        else:
            source = args.manifest.read_text(encoding="utf-8")
            if len(source) > 20_000:
                raise WheelHold("MANIFEST_TOO_LARGE")
            result, requirements = verify(args.wheelhouse, json.loads(source))
            if args.requirements_output is None:
                raise WheelHold("HASHED_REQUIREMENTS_OUTPUT_REQUIRED")
            args.requirements_output.write_text(requirements, encoding="utf-8")
            print(json.dumps(result, sort_keys=True))
        return 0
    except (WheelHold, OSError, UnicodeError, ValueError, TypeError):
        print("WHEEL_HASH_HOLD; production_recommendations=DISABLED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
