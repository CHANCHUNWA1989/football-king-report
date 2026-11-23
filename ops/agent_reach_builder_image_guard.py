"""Fail-closed Docker base-image digest gate for Agent Reach's OFFLINE builder.

A manifest must be separately committed after candidate digest discovery.
This parser only protects the reference structure; Docker's digest-addressed
pull performs the image integrity check. No publisher signature is attested.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SCHEMA = "agent-reach-builder-image-sha256-v1"
REPOSITORY = "docker.io/library/python"
OBSERVED_TAG = "3.12-slim"
PLATFORM = "linux/amd64"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ImageHold(ValueError):
    """Reject absent, malformed or unauthorized image records."""


def immutable_reference(manifest: object) -> str:
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema", "repository", "observed_tag", "platform", "digest"
    }:
        raise ImageHold("INVALID_IMAGE_LOCK_SCHEMA")
    if manifest["schema"] != SCHEMA:
        raise ImageHold("INVALID_IMAGE_LOCK_SCHEMA")
    if manifest["repository"] != REPOSITORY or manifest["observed_tag"] != OBSERVED_TAG:
        raise ImageHold("UNAUTHORIZED_IMAGE_SOURCE")
    if manifest["platform"] != PLATFORM:
        raise ImageHold("UNAUTHORIZED_IMAGE_PLATFORM")
    digest = manifest["digest"]
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ImageHold("INVALID_IMAGE_DIGEST")
    return REPOSITORY + "@" + digest


def read_manifest(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ImageHold("UNTRUSTED_MANIFEST_PATH")
    if path.stat().st_size > 4096:
        raise ImageHold("OVERSIZED_MANIFEST")
    return json.loads(path.read_text(encoding="utf-8"))


def acceptance() -> dict:
    return {
        "schema": "agent-reach-digest-lock-verification-v1",
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "reference_is_immutable": True,
        "registry_digest_download_independently_verified_by_this_parser": False,
        "publisher_signature_verified": False,
        "host_egress_firewall_verified": False,
        "source_timestamp_attested": False,
        "eligible_for_model": False,
        "verified_positive_ev": None,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--reference-only", action="store_true")
    args = p.parse_args()
    try:
        ref = immutable_reference(read_manifest(args.manifest))
    except (ImageHold, OSError, ValueError, UnicodeError, TypeError):
        print("BUILDER_IMAGE_HOLD; production_recommendations=DISABLED")
        return 2
    if args.reference_only:
        print(ref)
    else:
        print(json.dumps(acceptance(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
