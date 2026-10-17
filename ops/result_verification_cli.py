"""Offline CLI for auditable independent score checks; never modifies sealed evidence."""
import argparse
import json
import os
import tempfile
from pathlib import Path
from ops.result_verification_audit import audit_results

def main(argv=None):
    parser = argparse.ArgumentParser(description="Research-only result verification")
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--observations", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-input-bytes", type=int, default=10_000_000)
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.resolve() in {Path(args.fixtures).resolve(), Path(args.observations).resolve()}:
        parser.error("output must not overwrite input evidence")
    if args.max_input_bytes <= 0:
        parser.error("max-input-bytes must be positive")
    for input_path in (args.fixtures, args.observations):
        if Path(input_path).stat().st_size > args.max_input_bytes:
            parser.error("audit input exceeds size limit")
    fixtures = json.loads(Path(args.fixtures).read_text(encoding="utf-8"))
    observations = json.loads(Path(args.observations).read_text(encoding="utf-8"))
    result = audit_results(fixtures, observations)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".result-audit-", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return result

if __name__ == "__main__":
    main()
