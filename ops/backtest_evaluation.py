"""Offline, research-only chronological probability evaluation.

Requires independently verified pre-match snapshots. This module does not certify
positive EV, recommend wagers, or infer market probabilities from prices.
"""
from datetime import datetime, timezone
from decimal import Decimal
from math import log, isfinite
from ops.asian_settlement import settle

PRODUCTION_RECOMMENDATIONS = "DISABLED"
POSITIVE_EV_VERIFIED = False

def _prob(value):
    if isinstance(value, bool):
        raise ValueError("probability cannot be boolean")
    p = float(value)
    if not isfinite(p) or not 0 <= p <= 1:
        raise ValueError("probability must be finite and within [0,1]")
    return p

def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO8601 string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return dt.astimezone(timezone.utc)

def evaluate_binary(rows, *, min_train=1):
    """Time-ordered binary forecasts: outcome must be exactly 0 or 1.

    Each row: event_id, captured_at, kickoff_at, probability, outcome.
    Scores are out-of-sample only if caller supplies forecasts from a model
    fitted without future data; chronological order alone does not prove OOS.
    """
    if not isinstance(rows, (list, tuple)) or len(rows) < min_train + 1 or min_train < 1:
        raise ValueError("insufficient observations")
    prepared = []
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("row must be mapping")
        eid = row["event_id"]
        if not isinstance(eid, str) or not eid or eid in ids:
            raise ValueError("missing or duplicate event ID")
        ids.add(eid)
        captured, kickoff = _timestamp(row["captured_at"]), _timestamp(row["kickoff_at"])
        if captured >= kickoff:
            raise ValueError("forecast must be captured before kickoff")
        outcome = row["outcome"]
        if type(outcome) is not int or outcome not in (0, 1):
            raise ValueError("outcome must be binary integer")
        prepared.append((kickoff, captured, eid, _prob(row["probability"]), outcome))
    prepared.sort(key=lambda x: (x[0], x[2]))
    # Exclude initial chronological training segment from reported evaluation.
    holdout = prepared[min_train:]
    if any(prepared[i][0] == prepared[min_train][0] for i in range(min_train)):
        raise ValueError("training/holdout boundary shares kickoff time")
    n = len(holdout)
    brier = sum((p-y)**2 for _, _, _, p, y in holdout) / n
    eps = 1e-15
    logloss = -sum(y*log(max(eps, min(1-eps, p))) +
                   (1-y)*log(max(eps, min(1-eps, 1-p)))
                   for _, _, _, p, y in holdout) / n
    return {"holdout_count": n, "training_count": min_train,
            "brier": brier, "log_loss": logloss,
            "mean_forecast": sum(x[3] for x in holdout)/n,
            "observed_rate": sum(x[4] for x in holdout)/n,
            "out_of_sample_verified": False, "positive_ev_verified": False}

def evaluate_settled_returns(rows):
    """Aggregate recorded hypothetical settled returns, not a betting strategy.

    Each row: market, side, line, home_goals, away_goals, odds, stake.
    Does not estimate uncertainty, CLV or positive EV.
    """
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("nonempty rows required")
    staked = Decimal(0)
    net = Decimal(0)
    for row in rows:
        stake = Decimal(str(row["stake"]))
        if not stake.is_finite() or stake <= 0:
            raise ValueError("stake must be finite and positive")
        result = settle(row["market"], row["side"], row["line"],
                        row["home_goals"], row["away_goals"], row["odds"])
        staked += stake
        net += stake * result
    return {"count": len(rows), "staked": staked, "net": net,
            "roi": net/staked, "positive_ev_verified": False}
