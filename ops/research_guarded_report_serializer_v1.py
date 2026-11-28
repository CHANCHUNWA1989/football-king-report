"""Canonical, guarded serialization for research-only receipt reports."""
from __future__ import annotations
import json
from ops.research_receipt_export_guard_v1 import inspect_exported_receipt_report

def serialize_guarded_research_report(verification:dict)->bytes:
    if type(verification) is not dict:
        raise ValueError("verification mapping required")
    report=verification.get("research_report")
    if type(report) is not dict:
        raise ValueError("guarded research report missing")
    inspect_exported_receipt_report(verification,report)
    return (json.dumps(report,sort_keys=True,separators=(",",":"),
                       ensure_ascii=False,allow_nan=False)+"\n").encode("utf-8")
