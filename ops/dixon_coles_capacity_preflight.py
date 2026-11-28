"""Read-only, result-blind capacity diagnostics for the fixed D pilot.

No source requests, decompression, proof validation, or model scoring.
This cannot establish remote archive completeness or the cause of a past run.
"""
import argparse
import json
import os
from pathlib import Path

import dixon_coles_capture_history as history
import prepare_forecast_proof as existing


def inspect_capacity(root, *, run_id, attempt):
    out = dict(schema="football-king-dixon-capacity-v1", status="HOLD",
               reason="CATALOGUE_REJECTED", catalogue_valid=False,
               historical_count=None, historical_limit=history.MAX_HISTORY_CAPTURES,
               total_with_current=None, excess=None, capacity_ok=False,
               remote_history_completeness_verified=False, certified_case_count=0,
               production_recommendations="DISABLED")
    fd = None
    try:
        cutoff = history._key(run_id, attempt)
        fd = existing._open_directory(existing._absolute_path(root))
        catalogue = history._catalogue(fd)
        if not any(key == history.BASELINE for key, _, _ in catalogue):
            return {**out, "reason":"CAPTURE_HISTORY_BASELINE_MISSING"}
        count = sum(history.BASELINE <= key < cutoff for key, _, _ in catalogue)
        if history._catalogue(fd) != catalogue:
            return {**out, "reason":"CAPTURE_HISTORY_DIRECTORY_CHANGED"}
        limit = history.MAX_HISTORY_CAPTURES
        return {**out, "catalogue_valid":True, "historical_count":count,
                "total_with_current":count+1, "excess":max(0,count-limit),
                "capacity_ok":count<=limit,
                "reason":"WITHIN_CAPACITY_UNVERIFIED" if count<=limit else
                         "CAPTURE_HISTORY_COUNT_LIMIT"}
    except (OSError, ValueError, TypeError, KeyError, OverflowError,
            existing.PreparationError):
        return out
    finally:
        if fd is not None:
            os.close(fd)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-archives",type=Path,required=True)
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--attempt",required=True)
    args=parser.parse_args(argv)
    result=inspect_capacity(args.capture_archives,run_id=args.run_id,attempt=args.attempt)
    print(json.dumps(result,sort_keys=True))
    return 0 if result["capacity_ok"] else 1


if __name__=="__main__":
    raise SystemExit(main())
