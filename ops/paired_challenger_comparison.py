"""Offline same-fixture model comparison; research diagnostics never certify data.

Self-reported "independently_verified" and "sealed_before_kickoff" booleans
are not independent source or timestamp evidence. Neither synthetic tests
nor an improved model score may promote the cohort or produce betting tips.
"""
import argparse
import json
import math
from datetime import datetime, timezone


def _time(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("TIMEZONE_REQUIRED")
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError("INVALID_TIMESTAMP") from None


def _probabilities(values):
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError("INVALID_PROBABILITIES")
    if any(type(v) not in (float, int) or not math.isfinite(v)
           or v < 0 or v > 1 for v in values):
        raise ValueError("INVALID_PROBABILITIES")
    if abs(sum(values) - 1) > 1e-6:
        raise ValueError("INVALID_PROBABILITIES")
    return values


def _hold(reason, **extra):
    return {"status": "HOLD", "reason": reason,
            "production_recommendations": "DISABLED",
            "positive_ev_verified": False, "model_promoted": False,
            "independent_provenance_verified": False, **extra}


def evaluate(rows):
    """Compare all rows without dropping poor predictions or malformed events.

    A caller-provided flag is *not* external evidence. Local diagnostics
    are returned only with HOLD; they cannot certify independent results,
    timestamps, aligned market quotes, or profitable betting.
    """
    if not isinstance(rows, list) or not rows:
        return _hold("EMPTY_COHORT")
    if len(rows) > 50000:
        return _hold("COHORT_TOO_LARGE")
    seen = set()
    scores = {k: {"accuracy": 0., "log_loss": 0., "brier": 0.}
              for k in ("model_a", "challenger", "market")}
    try:
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "key", "kickoff_utc", "as_of_utc", "y", "model_a", "challenger",
                "market", "independently_verified", "sealed_before_kickoff"
            }:
                raise ValueError("INVALID_ROW_SCHEMA")
            key = row["key"]
            if not isinstance(key, str) or not key.strip() or key in seen:
                raise ValueError("DUPLICATE_OR_INVALID_KEY")
            seen.add(key)
            if (row["independently_verified"] is not True
                    or row["sealed_before_kickoff"] is not True):
                raise ValueError("UNVERIFIED_OR_UNSEALED")
            if not _time(row["as_of_utc"]) < _time(row["kickoff_utc"]):
                raise ValueError("LOOKAHEAD")
            y = row["y"]
            if type(y) is not int or y not in range(3):
                raise ValueError("INVALID_OUTCOME")
            for name, totals in scores.items():
                p = _probabilities(row[name])
                totals["accuracy"] += int(max(range(3), key=lambda i: p[i]) == y)
                totals["log_loss"] += -math.log(max(p[y], 1e-15))
                totals["brier"] += sum((v - int(i == y)) ** 2
                                       for i, v in enumerate(p))
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return _hold(str(exc))
    n = len(rows)
    diagnostics = {
        name: {metric: round(value / n, 6) for metric, value in totals.items()}
        for name, totals in scores.items()
    }
    return _hold("EXTERNAL_PROVENANCE_AND_QUOTE_ALIGNMENT_NOT_VERIFIED",
                 sample_count=n, unverified_diagnostic_metrics=diagnostics,
                 caller_flags_are_not_independent_evidence=True)


def _unique_json(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("DUPLICATE_JSON_KEY")
        values[key] = value
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as fh:
        payload = json.load(
            fh, object_pairs_hook=_unique_json,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    if not isinstance(payload, dict) or payload.get("schema") != "football-king-challenger-paired-v1":
        raise ValueError("INVALID_CONTRACT")
    print(json.dumps(evaluate(payload.get("rows")), indent=2,
                     ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
