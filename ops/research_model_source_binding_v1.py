"""Research-only model source fingerprint binding.

A digest of local source bytes detects drift during replay. It is not a signed
release, an independent attestation, or proof of market data authenticity.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Mapping
from ops.research_quote_archive_v1 import freeze_pricing_evidence,verify_pricing_evidence,_canonical

MODEL_FILES=(
    "ops/research_multimodel_v1.py",
    "ops/research_asian_settlement_v1.py",
    "ops/research_unified_pricing_v1.py",
    "ops/research_market_provenance_v1.py",
    "ops/research_evidence_bound_pricing_v1.py",
    "ops/research_quote_archive_v1.py",
)
def model_source_manifest(*, root: str | Path=".") -> dict:
    base=Path(root).resolve()
    entries={}
    for relative in MODEL_FILES:
        file=(base/relative).resolve()
        if not file.is_relative_to(base) or not file.is_file():
            raise ValueError("missing or unsafe model source: "+relative)
        entries[relative]=hashlib.sha256(file.read_bytes()).hexdigest()
    digest=hashlib.sha256(_canonical(entries).encode()).hexdigest()
    return {"schema":"football-king-model-source-manifest-v1",
            "files":entries,"sha256":digest}

def freeze_versioned_pricing_evidence(*, root: str | Path=".", **kwargs) -> dict:
    record=freeze_pricing_evidence(**kwargs)
    record["model_source_manifest"]=model_source_manifest(root=root)
    record.pop("sha256")
    record["sha256"]=hashlib.sha256(_canonical(record).encode()).hexdigest()
    return record

def verify_versioned_pricing_evidence(record: dict, *, root: str | Path=".") -> bool:
    try:
        if not isinstance(record,dict) or record.get("status")!="HOLD":
            return False
        manifest=record["model_source_manifest"]
        if manifest!=model_source_manifest(root=root):
            return False
        digest=record["sha256"]
        payload={k:v for k,v in record.items() if k!="sha256"}
        if hashlib.sha256(_canonical(payload).encode()).hexdigest()!=digest:
            return False
        underlying={k:v for k,v in record.items() if k!="model_source_manifest"}
        underlying.pop("sha256")
        underlying["sha256"]=hashlib.sha256(_canonical(underlying).encode()).hexdigest()
        return verify_pricing_evidence(underlying)
    except (ValueError,KeyError,TypeError,OSError,AttributeError):
        return False
