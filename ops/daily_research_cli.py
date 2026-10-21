"""Offline CLI for daily football research reports; never places bets.

Usage: python -m ops.daily_research_cli --input fixtures.json --output report.json
Input: {"generated_utc":"2026-10-21T10:00:00Z","rows":[...]}
No provider is connected; the caller must supply independently sourced rows.
"""
import argparse
import json
from pathlib import Path
from ops.daily_research_report import build_daily_research_report

def run(input_path, output_path):
    source = Path(input_path)
    destination = Path(output_path)
    if source.resolve() == destination.resolve():
        raise ValueError("INPUT_OUTPUT_PATH_COLLISION")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("INVALID_INPUT_PAYLOAD")
    report = build_daily_research_report(
        payload.get("rows"), generated_utc=payload.get("generated_utc"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    return report

def main():
    parser = argparse.ArgumentParser(description="Offline football research report (HOLD)")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.input, args.output)
    print("Research report written; production betting HOLD; "
          f"fixtures={result['sample_count']}")

if __name__ == "__main__":
    main()
