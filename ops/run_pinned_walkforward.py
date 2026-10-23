"""CLI for independently pinned, research-only football walk-forward diagnostics.

Usage: python ops/run_pinned_walkforward.py --history history.json
       --sha256 <externally-verified-sha256> --model-version v1
"""
import argparse
import json
from offline_pinned_walkforward import replay_pinned_walkforward


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--min-train", type=int, default=60)
    parser.add_argument("--test-size", type=int, default=30)
    parser.add_argument("--step-size", type=int, default=30)
    parser.add_argument("--embargo-hours", type=int, default=24)
    args = parser.parse_args(argv)
    report = replay_pinned_walkforward(
        args.history, expected_sha256=args.sha256,
        expected_model_version=args.model_version,
        min_train=args.min_train, test_size=args.test_size,
        step_size=args.step_size, embargo_hours=args.embargo_hours)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
