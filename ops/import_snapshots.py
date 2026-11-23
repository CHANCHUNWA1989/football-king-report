"""Research-only JSONL snapshot import gate. No provider access or betting actions."""
import argparse
import json
from pathlib import Path
from ops.evidence_coverage import evidence_coverage

def import_jsonl(path, *, max_rows=100000):
    path = Path(path)
    if max_rows < 1:
        raise ValueError("max_rows must be positive")
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            if len(rows) >= max_rows:
                raise ValueError("row limit exceeded")
            try:
                record = json.loads(line, parse_constant=lambda v: (_ for _ in ()).throw(ValueError("nonfinite JSON number")))
            except (ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid JSONL line {line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"JSONL line {line_number} must be an object")
            rows.append(record)
    return evidence_coverage(rows)

def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate research-only pre-match JSONL snapshots")
    parser.add_argument("input", help="JSON Lines file of pre-match snapshots")
    parser.add_argument("--max-rows", type=int, default=100000)
    args = parser.parse_args(argv)
    report = import_jsonl(args.input, max_rows=args.max_rows)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
