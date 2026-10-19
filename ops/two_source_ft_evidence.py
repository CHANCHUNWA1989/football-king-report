"""Report unverified FT agreement without manufacturing verified settlements."""
import argparse
import json
from pathlib import Path
from shadow_verified_adapter import observation_record


def evaluate(sealed, observations):
    if not isinstance(sealed, list) or not isinstance(observations, list):
        raise ValueError("INVALID_INPUT")
    seen = set()
    agreements = []
    for row in sealed:
        if not isinstance(row, dict) or not isinstance(row.get("fixture_id"), str):
            raise ValueError("INVALID_SEALED_ROW")
        key = row["fixture_id"]
        if key in seen:
            raise ValueError("DUPLICATE_SEALED_ROW")
        seen.add(key)
        if row.get("production_recommendations") != "DISABLED":
            raise ValueError("UNSAFE_SEALED_ROW")
        result = observation_record(row, observations)
        if result is not None:
            agreements.append(result)
    return {
        "schema": "football-king-two-source-ft-verification-v1",
        "sealed_fixture_count": len(sealed),
        "observation_count": len(observations),
        "two_source_verified_count": 0,
        "verified_records": [],
        "observation_consensus_count": len(agreements),
        "observation_records": agreements,
        "observation_status": "AGREED_UNVERIFIED" if agreements else "HOLD",
        "status": "HOLD",
        "external_provenance_rechecked": False,
        "independently_verified": False,
        "eligible_for_model_scoring": False,
        "eligible_for_betting_promotion": False,
        "reason": "TRUSTED_RESULT_EVIDENCE_VERIFIER_REQUIRED",
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
                      "observation_consensus_count": report["observation_consensus_count"],
                      "status": report["status"], "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
