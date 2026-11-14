"""Deterministic, fail-closed manifest for retrospective soccerdata research.

Manifest hashes exact canonical inputs, never authenticates upstream source,
result availability, forecast timing or licensing.
"""
import hashlib
import json
from ops.private_soccerdata_frequency_baseline import evaluate_frequency_baseline


def _digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_research_manifest(records, *, min_train=30, test_days=7):
    if not isinstance(records, list) or not records:
        raise ValueError("INVALID_HISTORY")
    result = evaluate_frequency_baseline(records, min_train=min_train, test_days=test_days)
    if result["production_recommendations"] != "DISABLED":
        raise ValueError("UNSAFE_BASELINE_RESULT")
    canonical = sorted(records, key=lambda r: r["source_index"])
    return {"schema": "football-king-retrospective-manifest-v1",
            "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "source": "soccerdata.MatchHistory", "source_records": len(records),
            "source_records_sha256": _digest(canonical),
            "settings": {"min_train": min_train, "test_days": test_days,
                         "smoothing": 1.0},
            "settings_sha256": _digest({"min_train": min_train, "test_days": test_days,
                                        "smoothing": 1.0}),
            "baseline_result_sha256": _digest(result),
            "baseline_summary": {k: result[k] for k in
                                 ("status", "production_recommendations",
                                  "fold_count", "prediction_count")},
            "independent_provenance_verified": False,
            "result_availability_verified": False,
            "odds_verified": False, "positive_ev_verified": False,
            "model_promoted": False,
            "note": "Hash consistency is not evidence of point-in-time authenticity."}


def verify_research_manifest(records, manifest):
    if not isinstance(manifest, dict) or manifest.get("schema") != "football-king-retrospective-manifest-v1":
        raise ValueError("INVALID_MANIFEST")
    settings = manifest.get("settings")
    if not isinstance(settings, dict) or set(settings) != {"min_train", "test_days", "smoothing"} or settings["smoothing"] != 1.0:
        raise ValueError("INVALID_MANIFEST_SETTINGS")
    expected = build_research_manifest(records, min_train=settings["min_train"],
                                       test_days=settings["test_days"])
    if manifest != expected:
        raise ValueError("RESEARCH_MANIFEST_MISMATCH")
    return {"status": "MATCH", "production_recommendations": "DISABLED",
            "independent_provenance_verified": False,
            "note": "Only input/output hash reproducibility verified."}
