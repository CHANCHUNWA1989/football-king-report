"""Offline CLI for auditable independent score checks; never modifies sealed evidence."""
import argparse
import json
from pathlib import Path
from ops.result_verification_audit import audit_results

def main(argv=None):
    parser = argparse.ArgumentParser(description="Research-only result verification")
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--observations", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    fixtures = json.loads(Path(args.fixtures).read_text(encoding="utf-8"))
    observations = json.loads(Path(args.observations).read_text(encoding="utf-8"))
    result = audit_results(fixtures, observations)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result

if __name__ == "__main__":
    main()
