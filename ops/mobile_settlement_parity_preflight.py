"""Offline iPhone report settlement-source parity preflight (research-only).

This runs the *actual* official-readiness and daily-scorecard builders in
memory against the candidate cumulative settlement document. It does not
change GitHub Actions, archived evidence, iPhone pages or production gates.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from ops.evidence_merge import validate
from ops.public_readiness_site import build as build_public_readiness
from ops.forward_daily_scorecard import build as build_daily_scorecard


class CutoverHold(ValueError):
    """Fail closed without logging identifiers, raw events or provider data."""


def preflight(legacy, candidate, gates, market, *, now=None):
    """Detect current-workflow split and prove both report builders agree
    when fed the SAME cumulative evidence, without writing any site assets.
    """
    old = validate(legacy)
    new = validate(candidate)
    old_index = {s["key"]: s for s in old}
    new_index = {s["key"]: s for s in new}
    if not set(old_index).issubset(new_index):
        raise CutoverHold("HISTORIC_SETTLEMENT_SAMPLE_MISSING")
    if any(new_index[k] != v for k, v in old_index.items()):
        raise CutoverHold("HISTORIC_SETTLEMENT_SAMPLE_MUTATED")

    if now is None:
        now = datetime.now(timezone.utc)
    # Exactly the builders used by the existing iPhone production workflow.
    legacy_public = build_public_readiness(legacy, gates, market, now=now)
    candidate_public = build_public_readiness(candidate, gates, market, now=now)
    candidate_daily = build_daily_scorecard(candidate)
    old_count = legacy_public["recorded_settled_cases"]
    new_public_count = candidate_public["recorded_settled_cases"]
    new_daily_count = candidate_daily["settled_observations"]

    if new_public_count != len(new) or new_daily_count != len(new):
        raise CutoverHold("MOBILE_BUILDERS_SETTLEMENT_COUNT_MISMATCH")

    safety = (
        legacy_public["status"] == "HOLD"
        and candidate_public["status"] == "HOLD"
        and candidate_public["official_recommendation_count"] == 0
        and candidate_public["independently_verified_result_cases"] == 0
        and candidate_daily["independently_verified_observations"] == 0
        and candidate_daily["results_independently_verified"] is False
        and candidate_daily["statistical_superiority_proven"] is False
        and candidate_public["production_recommendations"] == "DISABLED"
        and candidate_daily["production_recommendations"] == "DISABLED"
    )
    if not safety:
        raise CutoverHold("MOBILE_REPORTS_SAFETY_INVARIANT_FAILED")

    split = old_count != new_daily_count
    # Convergence here is a hypothetical same-input dry-run, NOT a switched
    # workflow. A split proves the present legacy/daily-source routing would
    # produce inconsistent cards if an isolated batch arrived.
    return {
        "schema": "football-king-mobile-settlement-parity-research-v1",
        "status": ("HOLD_CURRENT_WORKFLOW_SOURCE_SPLIT" if split else
                   "RESEARCH_PARITY_BASELINE_ONLY_NOT_DEPLOYED"),
        "legacy_main_public_readiness_count": old_count,
        "candidate_daily_scorecard_count": new_daily_count,
        "candidate_public_readiness_count_if_switched": new_public_count,
        "legacy_sample_count": len(old),
        "candidate_sample_count": len(new),
        "candidate_new_samples": len(new) - len(old),
        "current_workflow_count_parity": not split,
        "candidate_same_input_count_parity": new_public_count == new_daily_count,
        "source_switch_authorized": False,
        "production_recommendations": "DISABLED",
        "independent_result_verification_proven": False,
        "archive_branch_authenticated": False,
        "live_iphone_cutover_completed": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--gates", type=Path, required=True)
    parser.add_argument("--market", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        paths = (args.legacy, args.candidate, args.gates, args.market)
        if any(p.is_symlink() or not p.is_file() or p.stat().st_size > 8_000_000
               for p in paths):
            raise CutoverHold("UNSAFE_PARITY_INPUT")
        docs = [json.loads(p.read_bytes()) for p in paths]
        output = preflight(*docs)
        print(json.dumps(output, sort_keys=True))
        return 0 if output["current_workflow_count_parity"] else 1
    except (CutoverHold, ValueError, OSError, TypeError, KeyError):
        print(json.dumps({"status": "HOLD_MOBILE_SETTLEMENT_PARITY_NOT_CONFIRMED",
                          "production_recommendations": "DISABLED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
