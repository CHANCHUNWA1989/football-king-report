"""Quarantine manually collected FT notes; never convert to verified scores."""
import argparse
import json
from pathlib import Path

REQUIRED = {"date", "home", "away", "score_ft"}

def inspect(payload):
    if not isinstance(payload, dict):
        raise ValueError("INVALID_EVIDENCE")
    if payload.get("independently_verified") is not False or payload.get("eligible_for_model_scoring") is not False:
        raise ValueError("UNSAFE_EVIDENCE_FLAGS")
    if payload.get("status") != "HOLD" or payload.get("production_recommendations") != "DISABLED":
        raise ValueError("UNSAFE_PRODUCTION_FLAGS")
    rows = payload.get("matches")
    if not isinstance(rows, list):
        raise ValueError("INVALID_MATCH_LIST")
    for row in rows:
        if not isinstance(row, dict) or not REQUIRED.issubset(row):
            raise ValueError("INVALID_MATCH_ROW")
        score = row["score_ft"]
        if not isinstance(score, list) or len(score) != 2 or any(type(v) is not int or v < 0 or v > 30 for v in score):
            raise ValueError("INVALID_SCORE")
        if not all(isinstance(row[k], str) and row[k].strip() for k in ("date", "home", "away")):
            raise ValueError("INVALID_MATCH_IDENTITY")
    return {"status": "HOLD", "eligible_for_model_scoring": False,
            "production_recommendations": "DISABLED",
            "manual_evidence_count": len(rows),
            "verified_pairs_added": 0}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(json.loads(Path(args.input).read_text(encoding="utf-8")))))

if __name__ == "__main__":
    main()
