"""Chronological football 1X2 holdout with training-only prior baseline."""
from datetime import datetime, timezone
from ops.offline_1x2_validation import evaluate_1x2, OUTCOMES

def _utc(value):
    if not isinstance(value,str):
        raise ValueError("Missing kickoff")
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timezone required")
    return dt.astimezone(timezone.utc)

def holdout_1x2(rows, *, train_fraction=.7, min_test=2):
    if not 0<train_fraction<1 or type(min_test) is not int or min_test<1:
        raise ValueError("Invalid split")
    if len(rows)<min_test+2:
        raise ValueError("Insufficient events")
    times=[_utc(row["kickoff_at"]) for row in rows]
    if times!=sorted(times):
        raise ValueError("Kickoff times must be chronological")
    for row,t in zip(rows,times):
        forecast=_utc(row["forecast_at"])
        settled=_utc(row["settled_at"])
        if not forecast<t<settled:
            raise ValueError("Forecast must precede kickoff and settlement")
    split=int(len(rows)*train_fraction)
    if split<2 or len(rows)-split<min_test:
        raise ValueError("Insufficient split")
    train=rows[:split]
    test=rows[split:]
    # The training outcome prior must be knowable when the first holdout
    # prediction was issued, not merely before its kickoff.
    first_test_forecast=min(_utc(row["forecast_at"]) for row in test)
    if any(_utc(row["settled_at"])>=first_test_forecast for row in train):
        raise ValueError("Training outcomes were not settled before holdout forecast")
    ids=[row["event_id"] for row in rows]
    if any(not isinstance(event_id,str) or not event_id.strip() for event_id in ids):
        raise ValueError("Missing event ID")
    if len(set(ids))!=len(ids):
        raise ValueError("Duplicate event")
    prior={k:sum(row["outcome"]==k for row in train)/len(train) for k in OUTCOMES}
    baseline=[{"event_id":row["event_id"],"probabilities":prior,
               "outcome":row["outcome"]} for row in test]
    model=evaluate_1x2(test)
    benchmark=evaluate_1x2(baseline)
    brier_edge=benchmark["brier"]-model["brier"]
    logloss_edge=benchmark["log_loss"]-model["log_loss"]
    minimum_research_holdout=30
    enough_samples=len(test)>=minimum_research_holdout
    beats_baseline=brier_edge>0 and logloss_edge>0
    research_screen="REVIEW" if enough_samples and beats_baseline else "HOLD"
    research_reason=("requires_external_validation" if research_screen=="REVIEW"
                     else "insufficient_holdout_sample" if not enough_samples
                     else "fails_train_prior_baseline")
    return {"mode":"research","train_count":len(train),"test_count":len(test),
            "research_screen":research_screen,
            "research_screen_reason":research_reason,
            "minimum_research_holdout":minimum_research_holdout,
            "holdout":model,"train_prior_baseline":benchmark,
            "train_settlement_cutoff_verified":True,
            "holdout_brier_improvement_vs_train_prior":round(
                benchmark["brier"]-model["brier"],8),
            "holdout_logloss_improvement_vs_train_prior":round(
                benchmark["log_loss"]-model["log_loss"],8)}
