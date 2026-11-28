"""Research-only paired out-of-sample comparison and uncertainty.

Only paired, independently settled outcomes are accepted. No promotion.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from ops.research_multimodel_v1 import multiclass_brier,log_loss

@dataclass(frozen=True)
class PairedPrediction:
    event_id: str
    kickoff: datetime
    outcome: str
    baseline: dict[str,float]
    challenger: dict[str,float]
    independently_verified: bool

def paired_oos_report(samples: Sequence[PairedPrediction], *,
                      minimum_samples: int=300, block_size: int=20) -> dict:
    if minimum_samples<2 or block_size<1:
        raise ValueError("invalid validation policy")
    seen=set()
    prev=None
    deltas_brier=[]
    deltas_log=[]
    for s in samples:
        if not s.independently_verified or not s.event_id or s.event_id in seen:
            raise ValueError("unverified or duplicate match")
        if s.kickoff.tzinfo is None or s.kickoff.utcoffset() is None:
            raise ValueError("timezone-aware kickoff required")
        if prev is not None and s.kickoff<=prev:
            raise ValueError("strict chronological order required")
        seen.add(s.event_id)
        prev=s.kickoff
        deltas_brier.append(multiclass_brier(s.challenger,s.outcome)-multiclass_brier(s.baseline,s.outcome))
        deltas_log.append(log_loss(s.challenger,s.outcome)-log_loss(s.baseline,s.outcome))
    n=len(samples)
    def stats(d):
        if not d:return {"mean_delta":None,"block_se":None,"ci95":None}
        mean=sum(d)/len(d)
        blocks=[sum(d[i:i+block_size])/len(d[i:i+block_size])
                for i in range(0,len(d),block_size)]
        if len(blocks)<2:
            return {"mean_delta":mean,"block_se":None,"ci95":None}
        bmean=sum(blocks)/len(blocks)
        variance=sum((x-bmean)**2 for x in blocks)/(len(blocks)-1)
        se=math.sqrt(variance/len(blocks))
        return {"mean_delta":mean,"block_se":se,
                "ci95":[mean-1.96*se,mean+1.96*se]}
    b=stats(deltas_brier)
    l=stats(deltas_log)
    # CI is descriptive only; multiple testing, calibration, provenance and
    # independent holdout qualification are separate requirements.
    return {"schema":"football-king-paired-oos-v1","status":"HOLD",
            "production_recommendations":"DISABLED",
            "sample_count":n,"minimum_samples":minimum_samples,
            "minimum_sample_met":n>=minimum_samples,
            "brier":b,"log_loss":l,
            "challenger_better_on_both_means":(
                b["mean_delta"] is not None and b["mean_delta"]<0 and l["mean_delta"]<0),
            "independent_holdout_proven":False,
            "qualified_for_production":False}
