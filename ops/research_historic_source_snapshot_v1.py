"""Content-addressed historic source snapshot planning, without executing code.

The snapshot is a bytes-only immutable *value* handed to a future isolated
executor; no claim is made that an OS sandbox or durable store exists.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from ops.research_quote_archive_v1 import _canonical
from ops.research_model_source_binding_v1 import MODEL_FILES
from ops.research_historic_source_attestation_v1 import attest_historical_source

MAX_SOURCE_BYTES=2_000_000

def prepare_historic_source_snapshot(record: dict, *, historic_root: str | Path) -> dict:
    base={"status":"HOLD","production_recommendations":"DISABLED",
          "qualified_for_production":False,"execution_permitted":False,
          "snapshot_verified":False}
    attestation=attest_historical_source(record,historic_root=historic_root)
    if not attestation["historic_source_bytes_matched"]:
        return {**base,"reason":"SOURCE_ATTESTATION_FAILED"}
    try:
        root=Path(historic_root).absolute()
        files={}
        total=0
        for relative in MODEL_FILES:
            parts=[root]
            for component in Path(relative).parts:
                parts.append(parts[-1]/component)
            if any(p.is_symlink() for p in parts):
                raise ValueError("symlink")
            path=root/relative
            if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
                raise ValueError("outside root")
            content=path.read_bytes()
            total+=len(content)
            if total>MAX_SOURCE_BYTES:
                raise ValueError("source too large")
            digest=hashlib.sha256(content).hexdigest()
            if digest!=record["model_source_manifest"]["files"][relative]:
                raise ValueError("source changed during snapshot")
            files[relative]={"sha256":digest,"bytes_hex":content.hex()}
        snapshot={"schema":"football-king-historic-source-snapshot-v1",
                  "files":files,"source_manifest_sha256":record["model_source_manifest"]["sha256"]}
        snapshot["sha256"]=hashlib.sha256(_canonical(snapshot).encode()).hexdigest()
        return {**base,"reason":"SOURCE_SNAPSHOT_CAPTURED_NOT_EXECUTED",
                "snapshot_verified":True,"snapshot":snapshot}
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        return {**base,"reason":"SNAPSHOT_CAPTURE_FAILED"}

def verify_historic_source_snapshot(snapshot: dict, record: dict) -> bool:
    try:
        if type(record) is not dict or type(snapshot) is not dict:
            return False
        archive_payload={k:v for k,v in record.items() if k!="sha256"}
        if (type(record.get("sha256")) is not str
            or hashlib.sha256(_canonical(archive_payload).encode()).hexdigest()!=record["sha256"]):
            return False
        manifest=record["model_source_manifest"]
        if type(manifest) is not dict or type(manifest.get("files")) is not dict:
            return False
        if set(manifest["files"])!=set(MODEL_FILES):
            return False
        if (hashlib.sha256(_canonical(manifest["files"]).encode()).hexdigest()
            !=manifest.get("sha256")):
            return False
        if snapshot["schema"]!="football-king-historic-source-snapshot-v1":
            return False
        if snapshot["source_manifest_sha256"]!=record["model_source_manifest"]["sha256"]:
            return False
        files=snapshot["files"]
        if set(files)!=set(MODEL_FILES):
            return False
        total=0
        for relative in MODEL_FILES:
            item=files[relative]
            content=bytes.fromhex(item["bytes_hex"])
            total+=len(content)
            if total>MAX_SOURCE_BYTES:
                return False
            digest=hashlib.sha256(content).hexdigest()
            if digest!=item["sha256"] or digest!=record["model_source_manifest"]["files"][relative]:
                return False
        payload={k:v for k,v in snapshot.items() if k!="sha256"}
        return hashlib.sha256(_canonical(payload).encode()).hexdigest()==snapshot["sha256"]
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return False
