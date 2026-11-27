"""Non-executing historical model source attestation for archived research.

Only compares bytes and manifests. Never imports or executes historic source.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Mapping
from ops.research_quote_archive_v1 import _canonical
from ops.research_model_source_binding_v1 import MODEL_FILES
from ops.research_archive_compatibility_v1 import assess_archive_compatibility

def attest_historical_source(record: dict, *, historic_root: str | Path) -> dict:
    base={"status":"HOLD","production_recommendations":"DISABLED",
          "qualified_for_production":False,"historic_replay_verified":False,
          "historic_source_bytes_matched":False,"execution_permitted":False}
    try:
        # First authenticate the archive's own digest and manifest structure
        # against the current implementation, without demanding a version match.
        assessment=assess_archive_compatibility(record)
        if assessment["reason"]=="INVALID_OR_UNVERIFIABLE_ARCHIVE":
            return {**base,"reason":"INVALID_ARCHIVE"}
        root=Path(historic_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("not a directory")
        expected=record["model_source_manifest"]["files"]
        mismatches=[]
        for rel in MODEL_FILES:
            target=root/rel
            if target.is_symlink():
                mismatches.append(rel)
                continue
            resolved=target.resolve(strict=True)
            if not resolved.is_relative_to(root) or not resolved.is_file():
                mismatches.append(rel)
                continue
            if hashlib.sha256(resolved.read_bytes()).hexdigest()!=expected[rel]:
                mismatches.append(rel)
        if mismatches:
            return {**base,"reason":"HISTORIC_SOURCE_MISMATCH",
                    "mismatched_files":sorted(mismatches)}
        return {**base,"reason":"HISTORIC_SOURCE_BYTES_MATCH",
                "historic_source_bytes_matched":True,
                "mismatched_files":[]}
    except (KeyError,ValueError,TypeError,OSError,AttributeError):
        return {**base,"reason":"HISTORIC_SOURCE_UNAVAILABLE"}
