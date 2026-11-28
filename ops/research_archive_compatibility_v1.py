"""Fail-closed compatibility assessment for archived model-source manifests.

A historic archive can remain hash-intact while current source code has drifted.
Never silently migrate or reprice historic forecasts under a newer model.
"""
from __future__ import annotations
import hashlib
from ops.research_model_source_binding_v1 import (
    MODEL_FILES,model_source_manifest,verify_versioned_pricing_evidence)
from ops.research_quote_archive_v1 import _canonical

def assess_archive_compatibility(record: dict, *, root=".") -> dict:
    base={"status":"HOLD","production_recommendations":"DISABLED",
          "qualified_for_production":False,"historic_replay_verified":False,
          "migration_allowed":False}
    try:
        if not isinstance(record,dict):
            raise ValueError("invalid record")
        if record.get("status")!="HOLD" or record.get("qualified_for_production") is not False:
            raise ValueError("invalid safety status")
        if record.get("production_recommendations")!="DISABLED":
            raise ValueError("invalid production status")
        digest=record["sha256"]
        payload={k:v for k,v in record.items() if k!="sha256"}
        if not isinstance(digest,str) or len(digest)!=64 or hashlib.sha256(
                _canonical(payload).encode()).hexdigest()!=digest:
            raise ValueError("archive digest mismatch")
        historic=record["model_source_manifest"]
        files=historic["files"]
        if (historic.get("schema")!="football-king-model-source-manifest-v1"
            or set(files)!=set(MODEL_FILES)
            or any(not isinstance(x,str) or len(x)!=64 for x in files.values())
            or hashlib.sha256(_canonical(files).encode()).hexdigest()!=historic["sha256"]):
            raise ValueError("invalid source manifest")
        current=model_source_manifest(root=root)
        changed=sorted(k for k in MODEL_FILES if files[k]!=current["files"][k])
        if changed:
            return {**base,"reason":"MODEL_SOURCE_DRIFT",
                    "changed_files":changed,"current_source_sha256":current["sha256"],
                    "archived_source_sha256":historic["sha256"]}
        if not verify_versioned_pricing_evidence(record,root=root):
            raise ValueError("replay mismatch")
        return {**base,"reason":"EXACT_SOURCE_REPLAY_OK",
                "historic_replay_verified":True,"changed_files":[],
                "current_source_sha256":current["sha256"],
                "archived_source_sha256":historic["sha256"]}
    except (KeyError,ValueError,TypeError,AttributeError,OSError,OverflowError):
        return {**base,"reason":"INVALID_OR_UNVERIFIABLE_ARCHIVE",
                "changed_files":[]}
