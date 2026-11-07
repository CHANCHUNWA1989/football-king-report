"""Leakage-resistant expanding walk-forward 1X2 research audit.

Inspired by public descriptions of time-window backtesting; original code.
This audits pre-existing forecast vectors, NOT retraining a Poisson model.
Unverified data and local timestamps are diagnostics only; never actionable.
"""
from datetime import datetime, timezone

from ops.offline_1x2_validation import OUTCOMES, evaluate_1x2


def _utc(raw):
    if not isinstance(raw, str):
        raise ValueError("INVALID_TIME")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        raise ValueError("INVALID_TIME") from None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("NAIVE_TIME")
    return value.astimezone(timezone.utc)


def _hold(reason, **extra):
    return {"status": "HOLD", "reason": reason,
            "production_recommendations": "DISABLED",
            "positive_ev_verified": False, "independent_provenance_verified": False,
            "model_promoted": False, **extra}


def walk_forward(rows, *, min_train=20, test_size=10):
    """Evaluate every post-training fixture on adjacent chronological test folds.

    At each fold, baseline outcomes are sourced ONLY from events that were
    already settled before the earliest forecast in that fold. The baseline
    is a training-only 1X2 outcome frequency, not a betting-market proxy.
    Entire cohort fails closed on bad input or an unavailable training fold.

    Returns diagnostic scores with HOLD: the CSV schema cannot independently
    authenticate match results, model snapshots or the original timestamps.
    """
    if (type(min_train) is not int or type(test_size) is not int
            or min_train < 2 or test_size < 1):
        return _hold("INVALID_WINDOW_SPEC")
    if not isinstance(rows, list) or len(rows) < min_train + 1:
        return _hold("INSUFFICIENT_COHORT")
    if len(rows) > 50000:
        return _hold("COHORT_TOO_LARGE")

    try:
        seen = set()
        kickoffs, forecasts, settlements = [], [], []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("INVALID_ROW")
            event_id = row.get("event_id")
            if not isinstance(event_id, str) or not event_id.strip() or event_id in seen:
                raise ValueError("DUPLICATE_OR_INVALID_EVENT")
            seen.add(event_id)
            kickoff = _utc(row["kickoff_at"])
            forecast = _utc(row["forecast_at"])
            settled = _utc(row["settled_at"])
            if not forecast < kickoff < settled:
                raise ValueError("INVALID_EVENT_CHRONOLOGY")
            kickoffs.append(kickoff)
            forecasts.append(forecast)
            settlements.append(settled)
        if kickoffs != sorted(kickoffs):
            raise ValueError("NOT_CHRONOLOGICAL")
        # Evaluate solely to validate the complete input schema and outcomes;
        # these full-cohort scores are discarded, never used to fit a baseline.
        evaluate_1x2(rows)

        start = min_train
        # A simultaneous kickoff group must never straddle training/test.
        while start < len(rows) and kickoffs[start] == kickoffs[start - 1]:
            start += 1
        if start == len(rows):
            return _hold("NO_INTACT_TEST_WINDOW")

        model_test, prior_test, folds = [], [], []
        while start < len(rows):
            end = min(start + test_size, len(rows))
            while end < len(rows) and kickoffs[end] == kickoffs[end - 1]:
                end += 1

            first_forecast = min(forecasts[start:end])
            train_available = [rows[i] for i in range(start)
                               if settlements[i] < first_forecast]
            if len(train_available) < min_train:
                return _hold("TRAINING_RESULTS_UNAVAILABLE_AT_FORECAST",
                             blocked_fold=len(folds) + 1,
                             available_train=len(train_available),
                             required_train=min_train)

            prior = {name: sum(row["outcome"] == name for row in train_available)
                     / len(train_available) for name in OUTCOMES}
            test = rows[start:end]
            baseline = [{"event_id": row["event_id"],
                         "probabilities": dict(prior), "outcome": row["outcome"]}
                        for row in test]
            model_test.extend(test)
            prior_test.extend(baseline)
            folds.append({
                "fold": len(folds) + 1,
                "test_count": len(test),
                "train_available_count": len(train_available),
                "train_unavailable_at_cutoff": start - len(train_available),
                "first_test_forecast_utc": first_forecast.isoformat(),
                "first_test_kickoff_utc": kickoffs[start].isoformat(),
                "last_test_kickoff_utc": kickoffs[end - 1].isoformat(),
                "train_prior": prior,
                "model_diagnostic": evaluate_1x2(test),
                "prior_diagnostic": evaluate_1x2(baseline),
            })
            start = end

        model = evaluate_1x2(model_test)
        prior = evaluate_1x2(prior_test)
        return _hold(
            "INDEPENDENT_SOURCE_AND_FORECAST_PROVENANCE_NOT_VERIFIED",
            initial_training_count=len(rows) - len(model_test),
            evaluated_count=len(model_test),
            fold_count=len(folds),
            folds=folds,
            model_diagnostic=model,
            train_prior_diagnostic=prior,
            brier_improvement_vs_train_prior=round(prior["brier"] - model["brier"], 8),
            logloss_improvement_vs_train_prior=round(prior["log_loss"] - model["log_loss"], 8),
            note="Model forecasts are evaluated, not retrained; no source attestation or market-odds proof.",
        )
    except (ValueError, KeyError, TypeError, OverflowError, AttributeError, ZeroDivisionError) as exc:
        return _hold(str(exc))


__all__ = ["walk_forward"]
