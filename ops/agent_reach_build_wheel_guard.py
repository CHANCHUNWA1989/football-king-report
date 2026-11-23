"""Fail-closed SHA-256 integrity contract for Agent Reach wheel BUILD dependencies.

The manifest is trusted only after its values are independently committed.
New downloads must match those bytes; discovery NEVER validates itself.
This is distinct from runtime-wheel verification and does not prove authorship.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "agent-reach-build-wheel-sha256-v1"
EXPECTED = frozenset({"hatchling", "packaging", "pathspec", "pluggy", "trove-classifiers"})
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*\.whl\Z")
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")
VER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+]*\Z")
MAX_SIZE = 32_000_000


class BuildHold(ValueError):
    """Reject incomplete or inconsistent build wheel evidence."""


def identity(filename: object) -> tuple[str, str]:
    if not isinstance(filename, str) or len(filename) > 240 or not NAME_RE.fullmatch(filename):
        raise BuildHold("INVALID_WHEEL_NAME")
    fields = filename[:-4].split("-")
    if len(fields) not in (5, 6):
        raise BuildHold("INVALID_WHEEL_TAGS")
    name = re.sub(r"[-_.]+", "-", fields[0]).lower()
    version = fields[1]
    if name not in EXPECTED or not VER_RE.fullmatch(version):
        raise BuildHold("UNAPPROVED_BUILD_DEPENDENCY")
    if any(not part for part in fields[2:]):
        raise BuildHold("INVALID_WHEEL_TAGS")
    return name, version


def sha_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise BuildHold("UNSAFE_WHEEL_PATH")
    size = path.stat().st_size
    if size < 1 or size > MAX_SIZE:
        raise BuildHold("WHEEL_SIZE_OUT_OF_RANGE")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1_048_576), b""):
            h.update(chunk)
    return h.hexdigest()


def discover(wheel_dir: Path) -> dict:
    if wheel_dir.is_symlink() or not wheel_dir.is_dir():
        raise BuildHold("WHEELHOUSE_MISSING")
    seen = set()
    wheels = []
    for path in sorted(wheel_dir.iterdir()):
        if path.suffix != ".whl":
            raise BuildHold("NON_WHEEL_IN_DIRECTORY")
        name, _ = identity(path.name)
        if name in seen:
            raise BuildHold("DUPLICATE_BUILD_DEPENDENCY")
        seen.add(name)
        wheels.append({"file": path.name, "sha256": sha_file(path)})
    if seen != EXPECTED:
        raise BuildHold("BUILD_DEPENDENCY_INVENTORY_INCOMPLETE")
    return {"schema": SCHEMA, "wheels": wheels}


def verify(wheel_dir: Path, manifest: object) -> tuple[dict, str]:
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "wheels"} or manifest.get("schema") != SCHEMA:
        raise BuildHold("INVALID_COMMITTED_MANIFEST")
    rows = manifest.get("wheels")
    if not isinstance(rows, list) or len(rows) != len(EXPECTED):
        raise BuildHold("INVALID_COMMITTED_MANIFEST")
    approved: dict[str, tuple[str, str, str]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"file", "sha256"}:
            raise BuildHold("INVALID_COMMITTED_MANIFEST")
        name, version = identity(row.get("file"))
        digest = row.get("sha256")
        if not isinstance(digest, str) or not SHA_RE.fullmatch(digest) or name in approved:
            raise BuildHold("INVALID_COMMITTED_MANIFEST")
        approved[name] = (version, row["file"], digest)
    observed = discover(wheel_dir)
    if {r["file"]: r["sha256"] for r in rows} != {r["file"]: r["sha256"] for r in observed["wheels"]}:
        raise BuildHold("BUILD_WHEEL_SHA256_OR_FILE_CHANGED")
    requirements = "".join(
        f"{name}=={approved[name][0]} --hash=sha256:{approved[name][2]}\n"
        for name in sorted(EXPECTED)
    )
    report = {
        "schema": "agent-reach-offline-build-wheel-verification-v1",
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "build_dependency_wheel_sha256_matched": True,
        "build_dependency_wheel_count": len(approved),
        "offline_build_proved_by_this_step": False,
        "container_network_none_proved_by_this_step": False,
        "docker_image_digest_pinned": False,
        "upstream_signature_verified": False,
        "eligible_for_model": False,
        "verified_positive_ev": None,
    }
    return report, requirements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--discover-output", type=Path)
    mode.add_argument("--manifest", type=Path)
    parser.add_argument("--requirements-output", type=Path)
    args = parser.parse_args()
    try:
        if args.discover_output is not None:
            if args.requirements_output is not None:
                raise BuildHold("CANDIDATE_CANNOT_GENERATE_INSTALL_REQUIREMENTS")
            result = discover(args.wheelhouse)
            args.discover_output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print("BUILD_WHEEL_DISCOVERY_ONLY_NOT_VERIFIED; production_recommendations=DISABLED")
        else:
            raw = args.manifest.read_text(encoding="utf-8")
            if len(raw) > 20_000 or args.requirements_output is None:
                raise BuildHold("MANIFEST_TOO_LARGE_OR_NO_REQUIREMENTS_TARGET")
            report, requirements = verify(args.wheelhouse, json.loads(raw))
            args.requirements_output.write_text(requirements, encoding="utf-8")
            print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, BuildHold, UnicodeError, ValueError, TypeError):
        print("BUILD_WHEEL_HASH_HOLD; production_recommendations=DISABLED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
