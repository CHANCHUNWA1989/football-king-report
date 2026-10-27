"""Read-only European sports catalogue audit CLI.

Requires a locally supplied provider catalogue JSON file. Does not fetch
from providers, read credentials, spend API credits, or expose odds.
"""
import argparse
import json
from pathlib import Path

from ops.european_sports_catalogue import reconcile


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogue", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.catalogue.stat().st_size > 2_000_000:
            raise ValueError("CATALOGUE_TOO_LARGE")
        catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
        report = reconcile(catalogue)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        print(json.dumps({"status": "HOLD", "error_code": "INVALID_CATALOGUE",
                          "production_recommendations": "DISABLED"}))
        return 2
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
