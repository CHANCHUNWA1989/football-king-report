"""Apply existing two-source consensus gate to optional archived FT observations."""
import argparse
import json
from pathlib import Path
from shadow_verified_adapter import verified_record


def evaluate(sealed, observations):
    if not isinstance(sealed, list) or not isinstance(observations, list):
        raise ValueError("INVALID_INPUT")
    seen = set()
    verified = []
    for row in sealed:
        if not isinstance(row, dict) or not isinstance(row.get("fixture_id"), str):
            raise ValueError("INVALID_SEALED_ROW")
        key = row["fixture_id"]
        if key in seen:
            raise ValueError("DUPLICATE_SEALED_ROW")
        seen.add(key)
        if row.get("production_recommendations") != "DISABLED":
            raise ValueError("UNSAFE_SEALED_ROW")
        result = verified_record(row, observations)
        if result is not None:
            verified.append(result)
    return {
        "schema": "football-king-two-source-ft-verification-v1",
        "sealed_fixture_count": len(sealed),
        "observation_count": len(observations),
        "two_source_verified_count": len(verified),
        "verified_records": verified,
        "status": "RESEARCH_ONLY" if verified else "HOLD",
        "external_provenance_rechecked": False,
        "production_recommendations": "DISABLED",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sealed", required=True)
    p.add_argument("--observations")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    sealed = json.loads(Path(args.sealed).read_text(encoding="utf-8"))
    observations = json.loads(Path(args.observations).read_text(encoding="utf-8")) if args.observations else []
    report = evaluate(sealed, observations)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"two_source_verified_count": report["two_source_verified_count"],
                      "status": report["status"], "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
