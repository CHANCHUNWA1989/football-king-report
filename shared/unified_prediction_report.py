"""CLI report for verified research predictions; never claims trading performance."""
import argparse
import json
from pathlib import Path
from shared.unified_prediction_evaluation import evaluate_jsonl

def main(argv=None):
    parser = argparse.ArgumentParser(description="Research-only unified evaluation report")
    parser.add_argument("--predictions", required=True, help="JSONL forecast ledger")
    parser.add_argument("--outcomes", required=True, help="JSONL externally verified outcomes")
    parser.add_argument("--output", help="Optional JSON report path")
    args = parser.parse_args(argv)
    report = evaluate_jsonl(args.predictions, args.outcomes)
    result = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result + "\n", encoding="utf-8")
    print(result)
    return report

if __name__ == "__main__":
    main()
