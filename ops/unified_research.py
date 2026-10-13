"""Unified fail-closed daily research runner; no model promotion or betting."""
import argparse
import json
from pathlib import Path
from accuracy_bias_audit import audit
from market_shrinkage import compare
from model_evidence import read_rows


def run(path):
    result = {"status": "HOLD", "production_recommendations": "DISABLED",
              "accuracy_audit": None, "market_shrinkage": None}
    try:
        if not Path(path).is_file():
            result["reason"] = "NO_SEALED_PREDICTIONS"
            return result
        rows = read_rows(path)
        result["accuracy_audit"] = audit(rows)
        result["market_shrinkage"] = compare(rows)
        result["reason"] = "RESEARCH_ONLY_NOT_INDEPENDENTLY_VERIFIED"
    except (ValueError, OSError, TypeError, OverflowError, KeyError, ZeroDivisionError) as exc:
        result["reason"] = "INVALID_RESEARCH_INPUT_" + type(exc).__name__
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="inputs/shadow_predictions.csv")
    parser.add_argument("--output", default="unified-research-report.json")
    args = parser.parse_args()
    report = run(args.input)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "reason": report["reason"]}))
