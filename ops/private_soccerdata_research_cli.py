"""Offline CLI: produce reproducible research baseline from supplied MatchHistory JSON.

Usage: python -m ops.private_soccerdata_research_cli --input history.json
No downloading, bookmaker access, authentication or production recommendations.
"""
import argparse
import json
import sys
from ops.private_soccerdata_research_manifest import build_research_manifest
from ops.private_soccerdata_frequency_baseline import evaluate_frequency_baseline


def run(payload):
    if not isinstance(payload, dict) or set(payload) != {"schema", "records", "min_train", "test_days"}:
        raise ValueError("INVALID_RESEARCH_PAYLOAD")
    if payload["schema"] != "football-king-soccerdata-research-input-v1":
        raise ValueError("INVALID_RESEARCH_SCHEMA")
    records = payload["records"]
    min_train, test_days = payload["min_train"], payload["test_days"]
    baseline = evaluate_frequency_baseline(records, min_train=min_train, test_days=test_days)
    manifest = build_research_manifest(records, min_train=min_train, test_days=test_days)
    return {"schema": "football-king-soccerdata-research-output-v1",
            "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "manifest": manifest,
            "baseline": {k: v for k, v in baseline.items() if k != "predictions"},
            "independent_provenance_verified": False,
            "positive_ev_verified": False, "model_promoted": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to locally supplied JSON cohort")
    parser.add_argument("--output", help="Optional output path; stdout otherwise")
    args = parser.parse_args(argv)
    try:
        with open(args.input, encoding="utf-8") as f:
            payload = json.load(f)
        result = run(payload)
        rendered = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(rendered)
        else:
            sys.stdout.write(rendered)
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"RESEARCH_INPUT_REJECTED: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
