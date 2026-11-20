"""Fail-closed offline dataset provenance manifest.

A manifest is an audit aid, not evidence that an external source is authentic.
"""
import hashlib
import json
from pathlib import Path
from ops.import_snapshots import import_jsonl

def build_manifest(input_path, *, max_rows=100000):
    path = Path(input_path)
    coverage = import_jsonl(path, max_rows=max_rows)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "schema_version": 1,
        "input_filename": path.name,
        "input_sha256": digest.hexdigest(),
        "coverage": coverage,
        "source_authenticity_verified": False,
        "model_provenance_verified": False,
        "out_of_sample_verified": False,
        "positive_ev_verified": False,
        "production_recommendation_allowed": False,
    }

def write_manifest(input_path, output_path, *, max_rows=100000):
    """Write only a research report, never change model/betting configuration."""
    manifest = build_manifest(input_path, max_rows=max_rows)
    target = Path(output_path)
    if target.resolve() == Path(input_path).resolve():
        raise ValueError("output must not overwrite source")
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
