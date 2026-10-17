"""CLI report for verified research predictions; never claims trading performance."""
import argparse
import json
from pathlib import Path
import os
import tempfile
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
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".report-", suffix=".tmp", delete=False) as handle:
                temp_path = handle.name
                handle.write(result + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path is not None and os.path.exists(temp_path):
                os.unlink(temp_path)
    print(result)
    return report

if __name__ == "__main__":
    main()
