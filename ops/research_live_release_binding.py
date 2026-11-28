"""Local source fingerprint, not a signed build or runtime attestation."""
import hashlib
import platform
import sys
from pathlib import Path

FILES=("research_multimodel_v1.py","research_asian_settlement_v1.py",
       "research_unified_live_v2.py","research_live_evidence_v3.py",
       "research_live_intake_v4.py","research_live_calibration_v8.py",
       "research_live_pipeline_v10.py","research_live_release_binding.py")

def source_manifest():
    root=Path(__file__).resolve().parent
    files={}
    for name in FILES:
        path=root/name
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing or unsafe source")
        with path.open("rb") as stream:
            raw=stream.read(2_000_001)
        if not 0<len(raw)<=2_000_000:
            raise ValueError("invalid source size")
        files[name]=hashlib.sha256(raw).hexdigest()
    return {"schema":"live-local-source-manifest-v1","files":files,
            "python_implementation":platform.python_implementation(),
            "python_version":list(sys.version_info[:3])}
