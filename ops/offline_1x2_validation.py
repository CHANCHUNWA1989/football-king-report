"""Offline 1X2 forecast validation; research only, never betting advice."""
from math import isfinite, log, sqrt

OUTCOMES=("H","D","A")

def evaluate_1x2(rows):
    """Rows contain unique event_id, probabilities {H,D,A}, and settled outcome.

    Callers must supply verified pre-kickoff forecasts, not post-match estimates.
    """
    if not rows:
        raise ValueError("No settled forecasts")
    seen=set()
    brier=logloss=correct=0.0
    counts={k:0 for k in OUTCOMES}
    confidence_bins=[{"count":0,"sum_confidence":0.0,"correct":0} for _ in range(10)]
    for row in rows:
        event_id=row["event_id"]
        if not isinstance(event_id,str) or not event_id.strip() or event_id in seen:
            raise ValueError("Invalid or duplicate event")
        seen.add(event_id)
        outcome=row["outcome"]
        if outcome not in OUTCOMES:
            raise ValueError("Unsettled or invalid outcome")
        probs=row["probabilities"]
        if not isinstance(probs,dict) or set(probs)!=set(OUTCOMES):
            raise ValueError("Expected three 1X2 probabilities")
        if any(type(probs[k]) not in (int,float) or not isfinite(probs[k]) or not 0<=probs[k]<=1 for k in OUTCOMES):
            raise ValueError("Invalid probability")
        if abs(sum(probs.values())-1)>1e-6:
            raise ValueError("Probabilities must sum to one")
        brier+=sum((probs[k]-int(k==outcome))**2 for k in OUTCOMES)
        logloss-=log(max(probs[outcome],1e-15))
        winner=max(OUTCOMES,key=lambda k:probs[k])
        hit=int(winner==outcome)
        correct+=hit
        confidence=probs[winner]
        bucket=confidence_bins[min(int(confidence*10),9)]
        bucket["count"]+=1
        bucket["sum_confidence"]+=confidence
        bucket["correct"]+=hit
        counts[outcome]+=1
    n=len(rows)
    # Wilson 95% interval quantifies uncertainty of observed hit rate.
    z=1.959963984540054
    hit_rate=correct/n
    denom=1+z*z/n
    center=(hit_rate+z*z/(2*n))/denom
    margin=z*sqrt(hit_rate*(1-hit_rate)/n+z*z/(4*n*n))/denom
    accuracy_interval=[max(0.0,center-margin),min(1.0,center+margin)]
    confidence_calibration=[{"confidence_bin":i,"count":b["count"],
                             "mean_confidence":b["sum_confidence"]/b["count"],
                             "observed_accuracy":b["correct"]/b["count"]}
                            for i,b in enumerate(confidence_bins) if b["count"]]
    ece=sum(b["count"]*abs(b["sum_confidence"]/b["count"]-
            b["correct"]/b["count"]) for b in confidence_bins if b["count"])/n
    return {"mode":"research","sample_count":n,"brier":brier/n,
            "confidence_calibration_bins":confidence_calibration,
            "expected_confidence_calibration_error":ece,
            "log_loss":logloss/n,"accuracy":correct/n,"accuracy_wilson_95pct_interval":accuracy_interval,
            "majority_baseline_accuracy":max(counts.values())/n}
