"""V59 retrospective weight diagnostic, never a production fit or independent OOS."""
from datetime import timedelta
import hashlib
import math
from .research_candidate_gap_v6 import audit,stamp,vector
from .research_live_intake_v4 import decode
from .research_unified_prematch_replay_v35 import digest

WEIGHTS=tuple(i/10 for i in range(11))
EMBARGO=timedelta(days=7)
MIN_TRAIN=30
MIN_TEST=20
MIN_DAYS=5

def evaluate(raw,*,cutoff):
    out={"schema":"historical-weight-diagnostic-v59","status":"HOLD",
         "production_recommendations":"DISABLED","authenticated_samples":0,
         "training_admission":False,"qualified_for_production":False,
         "independent_oos_proven":False,"outcome_availability_proven":False,
         "market_same_cutoff_proven":False,"production_weights_fitted":False,
         "test_used_for_weight_selection":False,"descriptive_only":True,
         "diagnostic_completed":False}
    try:
        if audit(raw).get("structural_audit_passed") is not True:
            raise ValueError("ledger rejected")
        cut=stamp(cutoff)
        doc=decode(raw)
        if cut>=stamp(doc["checked_utc"]):
            raise ValueError("cutoff outside ledger")
        train=[]; test=[]
        for row in doc["samples"]:
            k,f=stamp(row["kickoff_utc"]),stamp(row["forecast_utc"])
            p,m=vector(row["p"]),vector(row["m"])
            y=row["y"]
            item=(k.date().isoformat(),row["key"],p,m,y)
            if k<cut-EMBARGO:
                train.append(item)
            elif f>=cut:
                test.append(item)
        train.sort(key=lambda x:x[1]);test.sort(key=lambda x:x[1])
        td=len({r[0] for r in train});vd=len({r[0] for r in test})
        out.update(ledger_sha256=hashlib.sha256(raw).hexdigest(),
                   cutoff=cut.isoformat(),embargo_days=7,train_n=len(train),
                   test_n=len(test),train_days=td,test_days=vd,
                   excluded_n=len(doc["samples"])-len(train)-len(test))
        if len(train)<MIN_TRAIN or len(test)<MIN_TEST or min(td,vd)<MIN_DAYS:
            out["reason"]="INSUFFICIENT_RETROSPECTIVE_COHORT"
            return out
        def score(rows,w):
            b=l=0.
            for _,_,p,m,y in rows:
                v=[w*x+(1-w)*z for x,z in zip(p,m)]
                total=sum(v)
                q=[x/total for x in v]
                b+=sum((x-(i==y))**2 for i,x in enumerate(q))
                l-=math.log(max(q[y],1e-15))
            return {"n":len(rows),"brier":b/len(rows),"log_loss":l/len(rows)}
        # Select solely on earlier rows; ties favor the market baseline.
        candidates=[(score(train,w)["log_loss"],w) for w in WEIGHTS]
        best_loss=min(loss for loss,_ in candidates)
        w=min(w for loss,w in candidates if loss<=best_loss+1e-12)
        policy={"schema":"retrospective-blend-policy-v59","cutoff":cut.isoformat(),
                "embargo_days":7,"model_weight":w,"training_count":len(train),
                "training_rows_sha256":digest(train),"candidate_weights":list(WEIGHTS),
                "outcome_availability_proven":False,"production_allowed":False}
        policy["sha256"]=digest(policy)
        out.update(diagnostic_completed=True,diagnostic_policy=policy,
                   training_scores=[{"weight":w0,"log_loss":loss} for loss,w0 in candidates],
                   test_metrics={"market":score(test,0),"model":score(test,1),
                                 "blend":score(test,w)},
                   notice="Retrospective recorded outcomes; embargo is not proof of availability. No production fit.")
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
        out["reason"]="INVALID_LEDGER_OR_CUTOFF"
    return out
