"""Real-score over-2.75 retrospective audit, NEVER a fake historical ROI.

The fixed 2026-10-31 public international-results Git blob contains actual
full-time scores for UEFA countries, but NO time-stamped bookmaker quotes,
pre-match odds, market opening/closing, or provider-origin certification.
This module only asks: if we had selected *all* real 2026 results and an
illustrative fixed decimal 1.78, how does over 2.75 settle? It is NOT a
tradable historical strategy or evidence of positive EV.

Training baseline 2025 remains independent of 2026 test outcomes. Counts
are unconditional; no result-conditioned selection, optimization or refits.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

from .live_uefa_nations_three_model_probe import (
    _read_source, _parse,
)

SCHEMA = "football-king-real-2026-over-275-retro-benchmark-v1"
# An ILLUSTRATION of the user's visible slip decimal price, not 186 observed
# tradable prices. Never claim bookie market history was actually retrieved.
ILLUSTRATIVE_DECIMAL = 1.78
MIN_TEST = 150


def score_over_275(score, *, decimal=ILLUSTRATIVE_DECIMAL):
    if (type(score) is not list or len(score) != 2
            or any(type(x) is not int or x < 0 or x > 20 for x in score)
            or type(decimal) not in (int,float)
            or not math.isfinite(decimal) or decimal <= 1):
        raise ValueError("INVALID_REAL_FT_OR_ILLUSTRATIVE_PRICE")
    total = sum(score)
    profit = decimal - 1
    if total <= 2:
        return ("FULL_LOSS", -1.0)
    if total == 3:
        # Half the stake on over-2.5 wins, half on over-3.0 pushes.
        return ("HALF_WIN", profit/2)
    return ("FULL_WIN", profit)


def aggregate(rows, *, decimal=ILLUSTRATIVE_DECIMAL):
    if type(rows) is not list or not rows:
        raise ValueError("EMPTY_REAL_SCORE_COHORT")
    results = [score_over_275(row["score_ft"],decimal=decimal) for row in rows]
    counts = {name:sum(1 for code,_ in results if code==name)
              for name in ("FULL_LOSS","HALF_WIN","FULL_WIN")}
    n = len(results)
    # For over 2.75: net = (decimal-1)*(P4 + 0.5*P3) - P0to2.
    roi = sum(net for _,net in results)/n
    full,half,loss=(counts["FULL_WIN"], counts["HALF_WIN"],
                    counts["FULL_LOSS"])
    factor=full+half/2
    fair=1+loss/factor if factor>0 else None
    return {
        "matches":n,
        "total_score_0_2":loss,
        "total_score_exactly_3":half,
        "total_score_4_or_more":full,
        "full_win_frequency":round(full/n,6),
        "half_win_frequency":round(half/n,6),
        "full_loss_frequency":round(loss/n,6),
        "hypothetical_fixed_decimal":decimal,
        "hypothetical_uniform_flat_stake_roi":round(roi,6),
        "historical_tradable_odds_collected":False,
        "empirical_fixed_price_breakeven_decimal_no_fees": (
            round(fair,6) if fair is not None else None),
        "no_confidence_or_profit_claim_from_unconditional_market":True,
    }


def audit(*, source_reader=_read_source):
    try:
        blob=source_reader()
        rows,source_last=_parse(blob)
        train=[r for r in rows
               if "2025-01-01"<=r["date"]<="2025-12-31"]
        test=[r for r in rows
              if "2026-01-01"<=r["date"]<="2026-10-06"]
        if not len(train)>=200 or len(test)<MIN_TEST:
            raise ValueError("REAL_2026_GOALS_COHORT_TOO_SMALL")
        if any(x["date"]>="2026-01-01" for x in train):
            raise ValueError("TEST_SCORE_LEAKAGE")
        if any(x["date"]<"2026-01-01" for x in test):
            raise ValueError("TRAIN_SCORE_LEAKAGE")
        return {
            "schema":SCHEMA,
            "status":"HOLD",
            "reason":"TRUE_RESULTS_ONLY_NO_HISTORICAL_MARKET_ODDS_OR_PREMATCH_GOAL_PROBABILITIES",
            "source_sha256_unattested":hashlib.sha256(blob).hexdigest(),
            "source_blob_git_sha_checked_in_source_reader":True,
            "dataset_last_actual_result_date":source_last.isoformat(),
            "training_split":"2025_real_results_only",
            "holdout_split":"2026_real_results_only_through_oct06",
            "true_retrospective_outcomes_not_forward_model_predictions":True,
            "training_2025":aggregate(train),
            "heldout_2026":aggregate(test),
            "bookmaker_quote_provenance_verified":False,
            "verified_market_edge_or_ev":False,
            "positive_ev_verified":False,
            "certified_prospective_goal_market_samples":0,
            "model_promoted":False,
            "production_recommendations":"DISABLED",
        }
    except Exception as exc:
        return {
            "schema":SCHEMA,"status":"HOLD",
            "reason":"REAL_GOAL_275_AUDIT_UNAVAILABLE",
            "safe_error_type":type(exc).__name__,
            "bookmaker_quote_provenance_verified":False,
            "verified_market_edge_or_ev":False,
            "positive_ev_verified":False,
            "certified_prospective_goal_market_samples":0,
            "model_promoted":False,
            "production_recommendations":"DISABLED",
        }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True)
    args=p.parse_args(argv)
    report=audit()
    path=Path(args.output)
    if path.exists() or path.is_symlink():
        raise ValueError("REFUSE_TO_OVERWRITE_GOAL_AUDIT")
    raw=(json.dumps(report,ensure_ascii=False,allow_nan=False,
                    sort_keys=True,separators=(",",":"))+"\n").encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL
               |getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    print("REAL_2026_GOALS_275_RETROSPECTIVE_AUDIT",raw.decode().strip())
    return 0 if "heldout_2026" in report and report["status"]=="HOLD" else 1


if __name__=="__main__":
    raise SystemExit(main())
