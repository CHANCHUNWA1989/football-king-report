"""Offline 1X2 forecast validation; research only, never betting advice."""
from math import isfinite, log

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
        correct+=int(max(OUTCOMES,key=lambda k:probs[k])==outcome)
        counts[outcome]+=1
    n=len(rows)
    return {"mode":"research","sample_count":n,"brier":brier/n,
            "log_loss":logloss/n,"accuracy":correct/n,
            "majority_baseline_accuracy":max(counts.values())/n}
