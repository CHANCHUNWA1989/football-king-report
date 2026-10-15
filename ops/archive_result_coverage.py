"""Offline diagnostic for sealed forecast coverage; never attests settlement provenance."""
import argparse
import json
from pathlib import Path


def audit(sealed, results):
    if not isinstance(sealed, list) or not isinstance(results, list):
        raise ValueError("INVALID_COLLECTION")
    ids = []
    for row in sealed:
        if not isinstance(row, dict) or not isinstance(row.get("fixture_id"), str) or not row["fixture_id"]:
            raise ValueError("INVALID_SEALED_FIXTURE")
        if row.get("production_recommendations") != "DISABLED":
            raise ValueError("UNSAFE_SEALED_FIXTURE")
        ids.append(row["fixture_id"])
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_SEALED_FIXTURE")
    observed = {}
    for row in results:
        if not isinstance(row, dict) or not isinstance(row.get("event_id"), str):
            raise ValueError("INVALID_RESULT_ID")
        key = row["event_id"]
        if key in observed:
            raise ValueError("DUPLICATE_RESULT_ID")
        observed[key] = row
    matched = [key for key in ids if key in observed]
    declared = sum(1 for key in matched if observed[key].get("independently_verified") is True
                   and observed[key].get("status") == "FINAL"
                   and observed[key].get("result") in ("H", "D", "A"))
    return {
        "schema": "football-king-archive-result-coverage-v1",
        "status": "HOLD",
        "sealed_forecasts": len(ids),
        "matching_result_ids": len(matched),
        "missing_result_ids": len(ids) - len(matched),
        "declared_verified_matches_not_audited": declared,
        "independently_attested_settlements": 0,
        "result_provenance": "NOT_AUDITED",
        "ready_for_production": False,
        "production_recommendations": "DISABLED",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sealed", required=True)
    p.add_argument("--results")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    sealed = json.loads(Path(args.sealed).read_text(encoding="utf-8"))
    results = json.loads(Path(args.results).read_text(encoding="utf-8")) if args.results else []
    report = audit(sealed, results)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
