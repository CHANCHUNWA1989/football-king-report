"""Offline same-fixture ensemble research audit. No authenticated data or picks.

A finite, predeclared weight family is selected by training log loss only.
The last chronological quarter is withheld, with all equal kickoffs intact.
Caller clocks are unverified; never generate new predictions or promote a model.
"""
from datetime import datetime, timedelta, timezone
import math
import re

MIN_TRAIN = 90
MIN_VALIDATION = 30
MIN_TRAIN_WEEKS = 8
MAX_ROWS = 10000
MAX_MODELS = 8
BLEND_WEIGHTS = (0.25, 0.5, 0.75)


def _hold(reason, **extra):
    return dict(status="HOLD", reason=reason, production_recommendations="DISABLED",
                formal_forward_eligible=False, independent_provenance_verified=False,
                positive_ev_verified=False, model_promoted=False,
                diagnostic_only=True, **extra)


def _clock(value):
    if type(value) is not str or len(value) > 64:
        raise ValueError("INVALID_TIMESTAMP")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("INVALID_TIMESTAMP")
    return dt.astimezone(timezone.utc)


def _vector(value):
    if (type(value) is not list or len(value) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   or not 0 <= v <= 1 for v in value)):
        raise ValueError("INVALID_PROBABILITIES")
    total = math.fsum(value)
    if abs(total - 1) > 1e-6:
        raise ValueError("INVALID_PROBABILITIES")
    return tuple(v / total for v in value)


def _metrics(rows, weights):
    losses, briers, hits = [], [], 0
    for row in rows:
        p = tuple(math.fsum(w * row["models"][name][i]
                            for name, w in weights.items()) for i in range(3))
        y = row["y"]
        losses.append(-math.log(max(p[y], 1e-15)))
        briers.append(math.fsum((v - int(i == y)) ** 2 for i, v in enumerate(p)))
        hits += int(max(range(3), key=lambda i: p[i]) == y)
    n = len(rows)
    return dict(log_loss=math.fsum(losses)/n, brier=math.fsum(briers)/n,
                accuracy=hits/n, sample_count=n)


def _weight_family(names):
    # No continuous optimizer or holdout-driven tuning; market-only included.
    family = [{name: float(name == selected) for name in names} for selected in names]
    for name in names:
        if name == "market":
            continue
        for w in BLEND_WEIGHTS:
            family.append({key: w if key == name else 1-w if key == "market" else 0.
                           for key in names})
    family.append({name: 1/len(names) for name in names})
    return family


def audit(rows):
    if type(rows) is not list or not MIN_TRAIN+MIN_VALIDATION <= len(rows) <= MAX_ROWS:
        return _hold("INSUFFICIENT_OR_OVERSIZED_COHORT")
    parsed, seen, names = [], set(), None
    try:
        for row in rows:
            if type(row) is not dict or set(row) != {
                "event_id", "kickoff_utc", "forecast_utc", "settled_utc",
                "market_utc", "y", "models", "production_recommendations"
            }:
                raise ValueError("INVALID_ROW")
            if row["production_recommendations"] != "DISABLED":
                raise ValueError("UNSAFE_ROW")
            key = row["event_id"]
            if type(key) is not str or not key.strip() or len(key) > 128 or key != key.strip():
                raise ValueError("INVALID_EVENT")
            if key in seen:
                raise ValueError("DUPLICATE_EVENT")
            seen.add(key)
            kick, forecast, settled, market = (_clock(row[k]) for k in
                ("kickoff_utc", "forecast_utc", "settled_utc", "market_utc"))
            if not (market <= forecast <= kick-timedelta(minutes=10)
                    and forecast-market <= timedelta(minutes=750)
                    and settled >= kick+timedelta(minutes=90)):
                raise ValueError("INVALID_CHRONOLOGY")
            models = row["models"]
            if (type(models) is not dict or not 2 <= len(models) <= MAX_MODELS
                    or "market" not in models or any(type(k) is not str or
                    not re.fullmatch(r"[a-z0-9_-]{1,64}", k) for k in models)):
                raise ValueError("INVALID_MODEL_SET")
            current = tuple(sorted(models))
            if names is None:
                names = current
            elif current != names:
                raise ValueError("MODEL_SET_MISMATCH")
            if type(row["y"]) is not int or row["y"] not in (0, 1, 2):
                raise ValueError("INVALID_OUTCOME")
            parsed.append(dict(key=key, kickoff=kick, forecast=forecast,
                               settled=settled, y=row["y"],
                               models={k: _vector(models[k]) for k in names}))
        parsed.sort(key=lambda row: (row["kickoff"], row["key"]))
        size = max(MIN_VALIDATION, len(parsed)//4)
        boundary = parsed[-size]["kickoff"]
        validation = [r for r in parsed if r["kickoff"] >= boundary]
        cutoff = min(r["forecast"] for r in validation)
        training = [r for r in parsed if r["kickoff"] < boundary and r["settled"] < cutoff]
        if len(training) < MIN_TRAIN:
            return _hold("INSUFFICIENT_PRIOR_SETTLEMENTS", train_count=len(training),
                         validation_count=len(validation))
        weeks = {r["kickoff"].isocalendar()[:2] for r in training}
        if len(weeks) < MIN_TRAIN_WEEKS:
            return _hold("INSUFFICIENT_TRAIN_WEEK_COVERAGE")
        family = _weight_family(names)
        scored = [(_metrics(training, w), w) for w in family]
        train_metrics, weights = min(scored, key=lambda pair: (
            pair[0]["log_loss"], pair[0]["brier"], -pair[1]["market"],
            tuple(pair[1][k] for k in names)))
        # Freeze weights before scoring any holdout outcomes.
        ensemble = _metrics(validation, weights)
        baselines = {k: _metrics(validation, {k: 1.0}) for k in names}
        market = baselines["market"]
        better = (ensemble["log_loss"] < market["log_loss"]
                  and ensemble["brier"] < market["brier"])
        return _hold("EXTERNAL_PROVENANCE_NOT_VERIFIED",
                     train_count=len(training), validation_count=len(validation),
                     training_week_count=len(weeks), tested_weight_candidates=len(family),
                     weights=weights, training_metrics=train_metrics,
                     validation=dict(ensemble=ensemble, **baselines),
                     both_scores_better_than_market=better,
                     training_cutoff_utc=cutoff.isoformat(),
                     validation_first_kickoff_utc=boundary.isoformat(),
                     holdout_used_for_weight_selection=False,
                     actual_prediction_issued=False)
    except (ValueError, TypeError, KeyError, OverflowError, ArithmeticError) as exc:
        return _hold(str(exc) or "INVALID_INPUT")
