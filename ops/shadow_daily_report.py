"""Offline daily four-model report from explicitly supplied sealed and FT JSON.

Input is intentionally not fetched from an unaudited URL. The collector must
supply real timestamped observations with provenance. No implicit backfill.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from shadow_verified_adapter import verified_record
from shadow_four_model_audit import evaluate

def report(sealed_rows, result_rows):
    if not isinstance(sealed_rows, list) or not isinstance(result_rows, list):
        raise ValueError("expected JSON lists")
    by_fixture = {}
    for obs in result_rows:
        if isinstance(obs, dict) and isinstance(obs.get("fixture_id"), str):
            by_fixture.setdefault(obs["fixture_id"], []).append(obs)
    valid = []
    for sealed in sealed_rows:
        if not isinstance(sealed, dict):
            continue
        fixture_id = sealed.get("fixture_id")
        row = verified_record(sealed, by_fixture.get(fixture_id, []))
        if row is not None:
            valid.append(row)
    scored = evaluate(valid)
    scored.update({
        "schema": "football-king-four-model-daily-shadow-1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "input_sealed_rows": len(sealed_rows),
        "input_result_observations": len(result_rows),
        "verified_candidates_before_dedup": len(valid),
        "source_policy": "AUTHENTICATED_ORIGINAL_RESULT_EVIDENCE_REQUIRED",
        "caller_consensus_is_not_verified_evidence": True,
        "status": "SHADOW_ONLY",
        "production_recommendations": "DISABLED",
        "note": "Research evidence only; no accuracy claims when sample_size is zero."
    })
    return scored

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sealed", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    sealed = json.loads(Path(args.sealed).read_text(encoding="utf-8"))
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    payload = report(sealed, results)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

if __name__ == "__main__":
    main()
